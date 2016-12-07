# channel data from device to host

The SPM002-C sends the spectrum data as follows in the payload. The CCD has an 12 bit ADC but each number is using 2 bytes (uint16).
There are 3648 pixel/channel.
Every 31 pixels are grouped together which results in '3648/31 ~ 118' groups. Each group starts with two bytes 0x31 0x60 (in total the 
chunck size of the group is 64 bytes).
the total number of bytes is 

117 * 31 (pixel per group) * 2 byte per pixel + 21  * 2 + 118 * 2 (headers )  = 7532

This data is divided into two usb packets of 4096+3436=7532



