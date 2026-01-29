"""
LadybugDB Compression Layer

BtrBlocks + Procella inspired compression:
- Dictionary encoding (dedup strings)
- Run-length encoding (repeated values)
- Frame-of-reference (small integers)
- Bitpacking (dense storage)
- Lazy decompression (decode on demand)

All Numba-optimized for zero-overhead decompression.
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union, Tuple, Iterator
from enum import IntEnum
import struct
import zlib

try:
    from numba import njit, prange, uint8, uint16, uint32, uint64, int32, int64
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if not args else decorator(args[0])
    prange = range


# =============================================================================
# ENCODING TYPES
# =============================================================================

class EncodingType(IntEnum):
    """Supported encoding types."""
    PLAIN = 0           # No compression
    DICTIONARY = 1      # Dictionary encoding
    RLE = 2            # Run-length encoding
    FOR = 3            # Frame of reference
    BITPACK = 4        # Bitpacking
    DELTA = 5          # Delta encoding
    ZSTD = 6           # Zstd compression
    HYBRID = 7         # Multiple encodings


# =============================================================================
# NUMBA-OPTIMIZED KERNELS
# =============================================================================

@njit(cache=True, fastmath=True)
def _rle_encode_kernel(data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Run-length encode array.
    Returns (values, run_lengths).
    """
    if len(data) == 0:
        return np.empty(0, dtype=data.dtype), np.empty(0, dtype=np.uint32)
    
    # Count runs
    n_runs = 1
    for i in range(1, len(data)):
        if data[i] != data[i-1]:
            n_runs += 1
    
    # Allocate output
    values = np.empty(n_runs, dtype=data.dtype)
    lengths = np.empty(n_runs, dtype=np.uint32)
    
    # Encode
    run_idx = 0
    values[0] = data[0]
    lengths[0] = 1
    
    for i in range(1, len(data)):
        if data[i] == data[i-1]:
            lengths[run_idx] += 1
        else:
            run_idx += 1
            values[run_idx] = data[i]
            lengths[run_idx] = 1
    
    return values, lengths


@njit(cache=True, fastmath=True, parallel=True)
def _rle_decode_kernel(values: np.ndarray, lengths: np.ndarray, 
                       out: np.ndarray) -> None:
    """Decode RLE in parallel."""
    # Compute offsets
    offsets = np.empty(len(lengths) + 1, dtype=np.int64)
    offsets[0] = 0
    for i in range(len(lengths)):
        offsets[i + 1] = offsets[i] + lengths[i]
    
    # Decode in parallel
    for i in prange(len(values)):
        start = offsets[i]
        end = offsets[i + 1]
        for j in range(start, end):
            out[j] = values[i]


@njit(cache=True, fastmath=True)
def _for_encode_kernel(data: np.ndarray) -> Tuple[np.ndarray, int64, uint8]:
    """
    Frame-of-reference encoding.
    Stores min value + deltas with minimal bit width.
    """
    if len(data) == 0:
        return np.empty(0, dtype=np.uint8), 0, 0
    
    min_val = data.min()
    max_delta = (data.max() - min_val)
    
    # Determine bit width needed
    if max_delta == 0:
        bit_width = 1
    else:
        bit_width = int(np.ceil(np.log2(max_delta + 1)))
    
    # Convert to deltas
    deltas = (data - min_val).astype(np.uint64)
    
    # Pack into bytes
    n_bytes = (len(data) * bit_width + 7) // 8
    packed = np.zeros(n_bytes, dtype=np.uint8)
    
    bit_pos = 0
    for i in range(len(data)):
        delta = deltas[i]
        for b in range(bit_width):
            if delta & (1 << b):
                byte_idx = bit_pos // 8
                bit_idx = bit_pos % 8
                packed[byte_idx] |= (1 << bit_idx)
            bit_pos += 1
    
    return packed, min_val, bit_width


@njit(cache=True, fastmath=True, parallel=True)
def _for_decode_kernel(packed: np.ndarray, min_val: int64, 
                       bit_width: uint8, n_values: int64,
                       out: np.ndarray) -> None:
    """Decode FOR in parallel."""
    for i in prange(n_values):
        delta = np.uint64(0)
        bit_start = i * bit_width
        
        for b in range(bit_width):
            bit_pos = bit_start + b
            byte_idx = bit_pos // 8
            bit_idx = bit_pos % 8
            if packed[byte_idx] & (1 << bit_idx):
                delta |= (np.uint64(1) << np.uint64(b))
        
        out[i] = min_val + delta


@njit(cache=True, fastmath=True)
def _delta_encode_kernel(data: np.ndarray) -> np.ndarray:
    """Delta encoding for sorted/sequential data."""
    if len(data) == 0:
        return np.empty(0, dtype=data.dtype)
    
    deltas = np.empty(len(data), dtype=data.dtype)
    deltas[0] = data[0]
    for i in range(1, len(data)):
        deltas[i] = data[i] - data[i-1]
    
    return deltas


@njit(cache=True, fastmath=True, parallel=True)
def _delta_decode_kernel(deltas: np.ndarray, out: np.ndarray) -> None:
    """Decode deltas (prefix sum)."""
    if len(deltas) == 0:
        return
    
    # Sequential prefix sum (parallel version is complex)
    out[0] = deltas[0]
    for i in range(1, len(deltas)):
        out[i] = out[i-1] + deltas[i]


@njit(cache=True, fastmath=True)
def _dictionary_encode_kernel(indices: np.ndarray, dict_size: int) -> Tuple[np.ndarray, uint8]:
    """
    Pack dictionary indices with minimal bits.
    """
    if dict_size <= 1:
        bit_width = 1
    else:
        bit_width = int(np.ceil(np.log2(dict_size)))
    
    n_bytes = (len(indices) * bit_width + 7) // 8
    packed = np.zeros(n_bytes, dtype=np.uint8)
    
    bit_pos = 0
    for i in range(len(indices)):
        idx = indices[i]
        for b in range(bit_width):
            if idx & (1 << b):
                byte_idx = bit_pos // 8
                bit_idx = bit_pos % 8
                packed[byte_idx] |= (1 << bit_idx)
            bit_pos += 1
    
    return packed, bit_width


@njit(cache=True, fastmath=True, parallel=True)
def _dictionary_decode_kernel(packed: np.ndarray, bit_width: uint8,
                              n_values: int64, out: np.ndarray) -> None:
    """Decode dictionary indices in parallel."""
    for i in prange(n_values):
        idx = np.uint32(0)
        bit_start = i * bit_width
        
        for b in range(bit_width):
            bit_pos = bit_start + b
            byte_idx = bit_pos // 8
            bit_idx = bit_pos % 8
            if packed[byte_idx] & (1 << bit_idx):
                idx |= (np.uint32(1) << np.uint32(b))
        
        out[i] = idx


# =============================================================================
# DICTIONARY BUILDER
# =============================================================================

class DictionaryBuilder:
    """
    Build string dictionary with deduplication.
    
    Usage:
        builder = DictionaryBuilder()
        indices = builder.add_many(["hello", "world", "hello", "foo"])
        # indices = [0, 1, 0, 2]  # "hello" deduped
        
        dictionary = builder.build()
        # dictionary = ["hello", "world", "foo"]
    """
    
    def __init__(self, max_size: int = 65536):
        self.max_size = max_size
        self._string_to_idx: Dict[str, int] = {}
        self._idx_to_string: List[str] = []
    
    def add(self, value: str) -> int:
        """Add string, return index."""
        if value in self._string_to_idx:
            return self._string_to_idx[value]
        
        idx = len(self._idx_to_string)
        if idx >= self.max_size:
            raise ValueError(f"Dictionary full (max {self.max_size})")
        
        self._string_to_idx[value] = idx
        self._idx_to_string.append(value)
        return idx
    
    def add_many(self, values: List[str]) -> np.ndarray:
        """Add many strings, return indices array."""
        indices = np.empty(len(values), dtype=np.uint32)
        for i, v in enumerate(values):
            indices[i] = self.add(v)
        return indices
    
    def build(self) -> List[str]:
        """Return the dictionary."""
        return list(self._idx_to_string)
    
    def __len__(self) -> int:
        return len(self._idx_to_string)
    
    def __contains__(self, value: str) -> bool:
        return value in self._string_to_idx


# =============================================================================
# COMPRESSED BLOCK
# =============================================================================

@dataclass
class CompressedBlock:
    """
    A compressed data block.
    
    Supports lazy decompression - only decode what's accessed.
    """
    encoding: EncodingType
    dtype: np.dtype
    n_values: int
    
    # Compressed data
    data: bytes
    
    # Metadata for specific encodings
    dictionary: Optional[List[str]] = None  # For DICTIONARY
    min_value: Optional[int] = None         # For FOR
    bit_width: Optional[int] = None         # For FOR/DICTIONARY
    
    # Cache for decoded data
    _decoded: Optional[np.ndarray] = field(default=None, repr=False)
    
    @property
    def compressed_size(self) -> int:
        """Size of compressed data in bytes."""
        return len(self.data)
    
    @property
    def uncompressed_size(self) -> int:
        """Size if uncompressed."""
        return self.n_values * self.dtype.itemsize
    
    @property
    def compression_ratio(self) -> float:
        """Compression ratio (higher = better)."""
        if self.compressed_size == 0:
            return float('inf')
        return self.uncompressed_size / self.compressed_size
    
    def decode(self) -> np.ndarray:
        """
        Decode the block.
        
        Uses cached result if available (lazy evaluation).
        """
        if self._decoded is not None:
            return self._decoded
        
        if self.encoding == EncodingType.PLAIN:
            self._decoded = np.frombuffer(self.data, dtype=self.dtype)
        
        elif self.encoding == EncodingType.DICTIONARY:
            # Decode indices
            packed = np.frombuffer(self.data, dtype=np.uint8)
            indices = np.empty(self.n_values, dtype=np.uint32)
            _dictionary_decode_kernel(packed, self.bit_width, self.n_values, indices)
            
            # Map to strings
            self._decoded = np.array([self.dictionary[i] for i in indices])
        
        elif self.encoding == EncodingType.RLE:
            # Unpack values and lengths
            half = len(self.data) // 2
            values = np.frombuffer(self.data[:half], dtype=self.dtype)
            lengths = np.frombuffer(self.data[half:], dtype=np.uint32)
            
            self._decoded = np.empty(self.n_values, dtype=self.dtype)
            _rle_decode_kernel(values, lengths, self._decoded)
        
        elif self.encoding == EncodingType.FOR:
            packed = np.frombuffer(self.data, dtype=np.uint8)
            self._decoded = np.empty(self.n_values, dtype=self.dtype)
            _for_decode_kernel(packed, self.min_value, self.bit_width, 
                              self.n_values, self._decoded)
        
        elif self.encoding == EncodingType.DELTA:
            deltas = np.frombuffer(self.data, dtype=self.dtype)
            self._decoded = np.empty(self.n_values, dtype=self.dtype)
            _delta_decode_kernel(deltas, self._decoded)
        
        elif self.encoding == EncodingType.ZSTD:
            decompressed = zlib.decompress(self.data)  # Using zlib as fallback
            self._decoded = np.frombuffer(decompressed, dtype=self.dtype)
        
        else:
            raise ValueError(f"Unknown encoding: {self.encoding}")
        
        return self._decoded
    
    def slice(self, start: int, end: int) -> np.ndarray:
        """
        Get a slice without decoding entire block.
        
        For some encodings, this can skip decoding unneeded data.
        """
        # For now, decode full block
        # TODO: Implement true lazy slicing for RLE, etc.
        return self.decode()[start:end]


# =============================================================================
# COMPRESSOR
# =============================================================================

class Compressor:
    """
    Intelligent compressor that selects best encoding.
    
    Usage:
        compressor = Compressor()
        
        # Compress with auto-selection
        block = compressor.compress(data)
        
        # Decompress
        original = block.decode()
    """
    
    def __init__(
        self,
        rle_threshold: float = 0.5,      # Min compression ratio for RLE
        dict_threshold: int = 256,        # Max unique values for dictionary
        for_bit_threshold: int = 16,      # Max bits for FOR
    ):
        self.rle_threshold = rle_threshold
        self.dict_threshold = dict_threshold
        self.for_bit_threshold = for_bit_threshold
    
    def compress(self, data: np.ndarray, force_encoding: Optional[EncodingType] = None) -> CompressedBlock:
        """
        Compress data with optimal encoding.
        
        Args:
            data: NumPy array to compress
            force_encoding: Force specific encoding (None = auto-select)
        
        Returns:
            CompressedBlock with compressed data
        """
        if force_encoding is not None:
            return self._compress_with_encoding(data, force_encoding)
        
        # Auto-select best encoding
        return self._auto_compress(data)
    
    def _auto_compress(self, data: np.ndarray) -> CompressedBlock:
        """Select best encoding automatically."""
        # Try each encoding and pick best
        candidates = []
        
        # Plain (baseline)
        plain = self._compress_plain(data)
        candidates.append(plain)
        
        # RLE (good for repeated values)
        if len(data) > 10:
            rle = self._compress_rle(data)
            if rle.compression_ratio >= self.rle_threshold:
                candidates.append(rle)
        
        # FOR (good for small integers)
        if np.issubdtype(data.dtype, np.integer):
            for_block = self._compress_for(data)
            if for_block.bit_width <= self.for_bit_threshold:
                candidates.append(for_block)
        
        # Delta (good for sorted/sequential)
        if np.issubdtype(data.dtype, np.integer):
            delta = self._compress_delta(data)
            candidates.append(delta)
        
        # Dictionary (good for strings or few unique values)
        if data.dtype.kind in ('U', 'S', 'O'):
            unique = set(str(x) for x in data)
            if len(unique) <= self.dict_threshold:
                dict_block = self._compress_dictionary(data)
                candidates.append(dict_block)
        
        # Pick best compression ratio
        return max(candidates, key=lambda b: b.compression_ratio)
    
    def _compress_plain(self, data: np.ndarray) -> CompressedBlock:
        """No compression."""
        return CompressedBlock(
            encoding=EncodingType.PLAIN,
            dtype=data.dtype,
            n_values=len(data),
            data=data.tobytes(),
        )
    
    def _compress_rle(self, data: np.ndarray) -> CompressedBlock:
        """Run-length encoding."""
        values, lengths = _rle_encode_kernel(data)
        
        return CompressedBlock(
            encoding=EncodingType.RLE,
            dtype=data.dtype,
            n_values=len(data),
            data=values.tobytes() + lengths.tobytes(),
        )
    
    def _compress_for(self, data: np.ndarray) -> CompressedBlock:
        """Frame-of-reference encoding."""
        packed, min_val, bit_width = _for_encode_kernel(data.astype(np.int64))
        
        return CompressedBlock(
            encoding=EncodingType.FOR,
            dtype=data.dtype,
            n_values=len(data),
            data=packed.tobytes(),
            min_value=int(min_val),
            bit_width=int(bit_width),
        )
    
    def _compress_delta(self, data: np.ndarray) -> CompressedBlock:
        """Delta encoding."""
        deltas = _delta_encode_kernel(data)
        
        return CompressedBlock(
            encoding=EncodingType.DELTA,
            dtype=data.dtype,
            n_values=len(data),
            data=deltas.tobytes(),
        )
    
    def _compress_dictionary(self, data: np.ndarray) -> CompressedBlock:
        """Dictionary encoding."""
        builder = DictionaryBuilder()
        
        # Convert to strings
        strings = [str(x) for x in data]
        indices = builder.add_many(strings)
        
        # Pack indices
        packed, bit_width = _dictionary_encode_kernel(indices, len(builder))
        
        return CompressedBlock(
            encoding=EncodingType.DICTIONARY,
            dtype=np.dtype('O'),  # Object dtype for strings
            n_values=len(data),
            data=packed.tobytes(),
            dictionary=builder.build(),
            bit_width=int(bit_width),
        )
    
    def compress_strings(self, strings: List[str]) -> CompressedBlock:
        """Convenience method for string compression."""
        return self._compress_dictionary(np.array(strings, dtype=object))


# =============================================================================
# COLUMN STORE (Procella-style)
# =============================================================================

@dataclass
class ColumnChunk:
    """A chunk of a column with compression."""
    column_name: str
    chunk_id: int
    block: CompressedBlock
    
    # Statistics for query pruning
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    null_count: int = 0
    distinct_count: Optional[int] = None


class ColumnStore:
    """
    Columnar storage with per-chunk compression.
    
    Procella-style:
    - Each column stored separately
    - Per-chunk compression
    - Statistics for query pruning
    - Lazy decompression
    
    Usage:
        store = ColumnStore()
        
        # Add data
        store.add_column("name", ["Alice", "Bob", "Alice", "Charlie"])
        store.add_column("age", [25, 30, 25, 35])
        
        # Query with pruning
        chunks = store.get_chunks("age", min_val=28)
        # Only returns chunks where max >= 28
    """
    
    def __init__(self, chunk_size: int = 10000):
        self.chunk_size = chunk_size
        self._columns: Dict[str, List[ColumnChunk]] = {}
        self._compressor = Compressor()
    
    def add_column(self, name: str, data: Union[np.ndarray, List]) -> None:
        """Add a column with automatic chunking and compression."""
        if not isinstance(data, np.ndarray):
            data = np.array(data)
        
        chunks = []
        n_chunks = (len(data) + self.chunk_size - 1) // self.chunk_size
        
        for i in range(n_chunks):
            start = i * self.chunk_size
            end = min(start + self.chunk_size, len(data))
            chunk_data = data[start:end]
            
            # Compress
            block = self._compressor.compress(chunk_data)
            
            # Compute statistics
            min_val = None
            max_val = None
            if np.issubdtype(chunk_data.dtype, np.number):
                min_val = float(chunk_data.min())
                max_val = float(chunk_data.max())
            
            chunk = ColumnChunk(
                column_name=name,
                chunk_id=i,
                block=block,
                min_value=min_val,
                max_value=max_val,
                null_count=int(np.sum(chunk_data == None)) if chunk_data.dtype == object else 0,
                distinct_count=len(np.unique(chunk_data)),
            )
            chunks.append(chunk)
        
        self._columns[name] = chunks
    
    def get_column(self, name: str) -> np.ndarray:
        """Get full column (decodes all chunks)."""
        if name not in self._columns:
            raise KeyError(f"Column not found: {name}")
        
        chunks = self._columns[name]
        arrays = [chunk.block.decode() for chunk in chunks]
        return np.concatenate(arrays)
    
    def get_chunks(
        self,
        name: str,
        min_val: Optional[Any] = None,
        max_val: Optional[Any] = None,
    ) -> List[ColumnChunk]:
        """
        Get chunks that might contain values in range.
        
        Uses statistics for pruning.
        """
        if name not in self._columns:
            raise KeyError(f"Column not found: {name}")
        
        chunks = []
        for chunk in self._columns[name]:
            # Prune based on statistics
            if min_val is not None and chunk.max_value is not None:
                if chunk.max_value < min_val:
                    continue  # Skip - all values below min
            
            if max_val is not None and chunk.min_value is not None:
                if chunk.min_value > max_val:
                    continue  # Skip - all values above max
            
            chunks.append(chunk)
        
        return chunks
    
    def stats(self) -> Dict[str, Dict[str, Any]]:
        """Get compression statistics."""
        stats = {}
        for name, chunks in self._columns.items():
            total_compressed = sum(c.block.compressed_size for c in chunks)
            total_uncompressed = sum(c.block.uncompressed_size for c in chunks)
            
            encodings = {}
            for c in chunks:
                enc_name = c.block.encoding.name
                encodings[enc_name] = encodings.get(enc_name, 0) + 1
            
            stats[name] = {
                'n_chunks': len(chunks),
                'compressed_size': total_compressed,
                'uncompressed_size': total_uncompressed,
                'compression_ratio': total_uncompressed / total_compressed if total_compressed > 0 else 0,
                'encodings': encodings,
            }
        
        return stats


# =============================================================================
# CHUNKING OPERATIONS
# =============================================================================

def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
    separator: str = '\n',
) -> List[str]:
    """
    Chunk text with overlap.
    
    Args:
        text: Text to chunk
        chunk_size: Target chunk size in characters
        overlap: Overlap between chunks
        separator: Preferred split point
    
    Returns:
        List of chunks
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        # Find end point
        end = start + chunk_size
        
        if end >= len(text):
            chunks.append(text[start:])
            break
        
        # Try to break at separator
        break_point = text.rfind(separator, start, end)
        if break_point > start:
            end = break_point + 1
        
        chunks.append(text[start:end])
        start = end - overlap
    
    return chunks


def chunk_tokens(
    tokens: List[str],
    chunk_size: int = 256,
    overlap: int = 32,
) -> List[List[str]]:
    """
    Chunk token list with overlap.
    
    Args:
        tokens: List of tokens
        chunk_size: Tokens per chunk
        overlap: Token overlap
    
    Returns:
        List of token chunks
    """
    if len(tokens) <= chunk_size:
        return [tokens]
    
    chunks = []
    start = 0
    
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunks.append(tokens[start:end])
        start = end - overlap
        
        if start >= len(tokens):
            break
    
    return chunks


def semantic_chunk(
    text: str,
    min_chunk: int = 100,
    max_chunk: int = 1000,
) -> List[str]:
    """
    Chunk text at semantic boundaries (sentences, paragraphs).
    
    Args:
        text: Text to chunk
        min_chunk: Minimum chunk size
        max_chunk: Maximum chunk size
    
    Returns:
        List of semantic chunks
    """
    import re
    
    # Split into paragraphs
    paragraphs = re.split(r'\n\n+', text)
    
    chunks = []
    current_chunk = ""
    
    for para in paragraphs:
        if len(current_chunk) + len(para) <= max_chunk:
            current_chunk += para + "\n\n"
        else:
            if current_chunk and len(current_chunk) >= min_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
            elif len(para) > max_chunk:
                # Split long paragraph by sentences
                sentences = re.split(r'(?<=[.!?])\s+', para)
                for sent in sentences:
                    if len(current_chunk) + len(sent) <= max_chunk:
                        current_chunk += sent + " "
                    else:
                        if current_chunk and len(current_chunk) >= min_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sent + " "
            else:
                current_chunk = para + "\n\n"
    
    if current_chunk and len(current_chunk) >= min_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks
