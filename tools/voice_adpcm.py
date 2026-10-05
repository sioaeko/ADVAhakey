"""Decode ADV's independently framed 320-sample IMA ADPCM voice blocks."""
import struct

STEPS = (7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,60,66,73,80,88,97,107,118,130,143,157,173,190,209,230,253,279,307,337,371,408,449,494,544,598,658,724,796,876,963,1060,1166,1282,1411,1552,1707,1878,2066,2272,2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,7132,7845,8630,9493,10442,11487,12635,13899,15289,16818,18500,20350,22385,24623,27086,29794,32767)
INDEX = (-1,-1,-1,-1,2,4,6,8)


def decode_adpcm(block):
    if len(block) != 163 or block[2] > 88 or block[-1] & 0xf0:
        raise ValueError('Invalid ADV IMA ADPCM block')
    predicted = struct.unpack_from('<h', block)[0]
    index = block[2]
    pcm = [predicted]
    for n in range(319):
        code = (block[3+n//2] >> ((n & 1)*4)) & 15
        step = STEPS[index]
        difference = (step >> 3) + (step if code & 4 else 0) + (step >> 1 if code & 2 else 0) + (step >> 2 if code & 1 else 0)
        predicted = max(-32768, min(32767, predicted + (-difference if code & 8 else difference)))
        index = max(0, min(88, index + INDEX[code & 7]))
        pcm.append(predicted)
    return struct.pack('<320h', *pcm)
