# Taken from https://github.com/acida/pyima
# Modified by me

import struct

T_INDEX = [-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8]  # index table

T_STEP = [
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    16,
    17,
    19,
    21,
    23,
    25,
    28,
    31,
    34,
    37,
    41,
    45,
    50,
    55,
    60,
    66,
    73,
    80,
    88,
    97,
    107,
    118,
    130,
    143,
    157,
    173,
    190,
    209,
    230,
    253,
    279,
    307,
    337,
    371,
    408,
    449,
    494,
    544,
    598,
    658,
    724,
    796,
    876,
    963,
    1060,
    1166,
    1282,
    1411,
    1552,
    1707,
    1878,
    2066,
    2272,
    2499,
    2749,
    3024,
    3327,
    3660,
    4026,
    4428,
    4871,
    5358,
    5894,
    6484,
    7132,
    7845,
    8630,
    9493,
    10442,
    11487,
    12635,
    13899,
    15289,
    16818,
    18500,
    20350,
    22385,
    24623,
    27086,
    29794,
    32767,
]  # quantize table


class PyIma:
    def __init__(self):
        self._encoder_predicted = 0
        self._encoder_index = 0
        self._decoder_predicted = 0
        self._decoder_index = 0
        self._decoder_step = 7

    def _encode_sample(self, sample: int):
        # encode one linear pcm sample to ima adpcm neeble
        assert isinstance(sample, int)
        delta = sample - self._encoder_predicted

        if delta >= 0:
            value = 0
        else:
            value = 8
            delta = -delta

        step = T_STEP[self._encoder_index]

        diff = step >> 3

        if delta > step:
            value |= 4
            delta -= step
            diff += step
        step >>= 1

        if delta > step:
            value |= 2
            delta -= step
            diff += step
        step >>= 1

        if delta > step:
            value |= 1
            diff += step

        if value & 8:
            self._encoder_predicted -= diff
        else:
            self._encoder_predicted += diff

        if self._encoder_predicted < -0x8000:
            self._encoder_predicted = -0x8000
        elif self._encoder_predicted > 0x7FFF:
            self._encoder_predicted = 0x7FFF

        self._encoder_index += T_INDEX[value & 7]

        if self._encoder_index < 0:
            self._encoder_index = 0
        elif self._encoder_index > 88:
            self._encoder_index = 88

        return value

    def _decode_sample(self, neeble: int):
        # decode one sample from compressed neeble

        difference = 0

        if neeble & 4:
            difference += self._decoder_step

        if neeble & 2:
            difference += self._decoder_step >> 1

        if neeble & 1:
            difference += self._decoder_step >> 2

        difference += self._decoder_step >> 3

        if neeble & 8:
            difference = -difference

        self._decoder_predicted += difference

        if self._decoder_predicted > 32767:
            self._decoder_predicted = 32767

        elif self._decoder_predicted < -32767:
            self._decoder_predicted = -32767

        self._decoder_index += T_INDEX[neeble]
        if self._decoder_index < 0:
            self._decoder_index = 0
        elif self._decoder_index > 88:
            self._decoder_index = 88
        self._decoder_step = T_STEP[self._decoder_index]

        return self._decoder_predicted

    def _calc_head(self, sample: bytes):
        # Calculating ima adpcm block head
        self._encode_sample(struct.unpack("h", sample)[0])
        # packing header
        head = sample  # Uncompressed sample
        head += struct.pack("B", self._encoder_index)  # Calculated index for sample
        head += struct.pack("B", 0x00)  # Always 0
        return head

    def encode_block(self, block: bytes):
        """Encode linear pcm fragment to compressed ima adpcm block.
        Block is a string containing values from wavefile, network, etc.
        Returns a string containing packed compressed ima adpcm block.
        Only 1010 bytes size linear mono 16 bit fragment supported."""
        if len(block) != 1010:
            raise ValueError("Unsupported sample quantity in block. Should be 505.")

        result = self._calc_head(block[0:2])

        for i in range(2, len(block)):

            if (i + 1) % 4 == 0:

                sample2 = self._encode_sample(
                    struct.unpack("h", block[i - 1 : i + 1 :])[0]
                )
                sample = self._encode_sample(
                    struct.unpack("h", block[i + 1 : i + 3 :])[0]
                )
                result += struct.pack("B", (sample << 4) | sample2)

        return result

    def decode_block(self, block: bytes):
        """Decode compressed ima adpcm block.
        Block is a string containing packed values from wavefile, network, etc.
        Returns a string containing packed uncompressed linear pcm values.
        Only 256 bytes compressed block size supported."""
        if len(block) != 256:
            raise ValueError("Unsupported block size. Should be 256.")

        result = b""
        self._decoder_predicted = struct.unpack("h", block[0:2])[0]
        self._decoder_index: int = struct.unpack("B", block[2:3])[0]
        self._decoder_step = T_STEP[self._decoder_index]
        result += block[0:2]

        for i in range(4, len(block)):
            original_sample = struct.unpack("B", block[i : i + 1])[0]
            second_sample = original_sample >> 4
            first_sample = (second_sample << 4) ^ original_sample
            result += struct.pack("h", self._decode_sample(first_sample))
            result += struct.pack("h", self._decode_sample(second_sample))

        return result
