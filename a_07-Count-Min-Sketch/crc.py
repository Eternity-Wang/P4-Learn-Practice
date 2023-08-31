import struct

class Crc(object):
    """
    A base class for CRC routines.
    """
    # pylint: disable=too-many-instance-attributes

    def __init__(self, width, poly, reflect_in, xor_in, reflect_out, xor_out, table_idx_width=None, slice_by=1):
        """The Crc constructor.

        其具有如下参数:
            width
            poly
            reflect_in
            xor_in
            reflect_out
            xor_out
        """
        # pylint: disable=too-many-arguments

        self.width = width
        self.poly = poly
        self.reflect_in = reflect_in
        self.xor_in = xor_in
        self.reflect_out = reflect_out
        self.xor_out = xor_out
        self.tbl_idx_width = table_idx_width
        self.slice_by = slice_by

        self.msb_mask = 0x1 << (self.width - 1)
        self.mask = ((self.msb_mask - 1) << 1) | 1
        if self.tbl_idx_width != None:
            self.tbl_width = 1 << self.tbl_idx_width
        else:
            self.tbl_idx_width = 8
            self.tbl_width = 1 << self.tbl_idx_width

        self.direct_init = self.xor_in
        self.nondirect_init = self.__get_nondirect_init(self.xor_in)
        if self.width < 8:
            self.crc_shift = 8 - self.width
        else:
            self.crc_shift = 0


    def __get_nondirect_init(self, init):
        """
        return the non-direct init if the direct algorithm has been selected.
        """
        crc = init
        for dummy_i in range(self.width):
            bit = crc & 0x01
            if bit:
                crc ^= self.poly
            crc >>= 1
            if bit:
                crc |= self.msb_mask
        return crc & self.mask


    def reflect(self, data, width):
        """
        reflect a data word, i.e. reverts the bit order.
        """
        # pylint: disable=no-self-use

        res = data & 0x01
        for dummy_i in range(width - 1):
            data >>= 1
            res = (res << 1) | (data & 0x01)
        return res


    def bit_by_bit(self, in_data):
        """
        经典的简单且缓慢的 CRC 实现。该函数逐位迭代增强的输入消息，并在最后返回计算出的 CRC 值。
        """

        reg = self.nondirect_init
        for octet in in_data:
            if self.reflect_in:
                octet = self.reflect(octet, 8)
            for i in range(8):
                topbit = reg & self.msb_mask
                reg = ((reg << 1) & self.mask) | ((octet >> (7 - i)) & 0x01)
                if topbit:
                    reg ^= self.poly

        for i in range(self.width):
            topbit = reg & self.msb_mask
            reg = ((reg << 1) & self.mask)
            if topbit:
                reg ^= self.poly

        if self.reflect_out:
            reg = self.reflect(reg, self.width)
        return (reg ^ self.xor_out) & self.mask


    def bit_by_bit_fast(self, in_data):
        """
        这是 bit-by-bit 算法的稍微修改版本: 它不需要循环增强位(augmented bits),
        即在 bit-by-bit 算法中附加到输入消息的宽度 0 位。
        """

        reg = self.direct_init
        for octet in in_data:
            if self.reflect_in:
                octet = self.reflect(octet, 8)
            for i in range(8):
                topbit = reg & self.msb_mask
                if octet & (0x80 >> i):
                    topbit ^= self.msb_mask
                reg <<= 1
                if topbit:
                    reg ^= self.poly
            reg &= self.mask
        if self.reflect_out:
            reg = self.reflect(reg, self.width)
        return reg ^ self.xor_out