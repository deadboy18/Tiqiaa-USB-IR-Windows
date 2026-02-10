# Reverse Engineering the Protocol of a Chinese USB IR Transceiver

* **Original Article:** [Habr: Реверс-инжениринг протокола китайского USB ИК трансивера](https://habr.com/ru/articles/494800/)
* **Original Author:** [XenRE](https://habr.com/ru/users/XenRE/)
* **Source Code:** [GitLab: Tiqiaa USB IR](https://gitlab.com/XenRE/tiqiaa-usb-ir/-/tree/master?ref_type=heads)
* **Translator's Note:** *This is a translation of the original Russian article into English.*

---

<img width="780" height="243" alt="image" src="https://github.com/user-attachments/assets/1e97714b-b28e-4a40-8c94-2bbbafe29c8f" />


I came across a Chinese MicroUSB IR transceiver, and I had the desire to connect it to a Windows PC. The transceiver is a very compact device with a Micro USB connector. The only "official" way to work with it is through an Android application called **ZaZaRemote**.

When connected to a computer via an adapter, the device was identified as an HID-compliant device `USB\VID_10C4&PID_8468`. Googling this ID gave no results, so I had to resort to reverse-engineering the protocol.

## Incorrect HID

The device class was defined as `USB\Class_03&SubClass_FF&Prot_FF`.

* `Class_03` — HID device.
* `SubClass_FF` — Vendor specific.

The system automatically installed the `hidusb.sys` driver. With this driver, it is possible to work via the [HID API](https://docs.microsoft.com/en-us/windows-hardware/drivers/ddi/hidsdi/).

After sketching out a simple program, I was able to get various info about the device:

```text
HidD_GetManufacturerString: "Tiqiaa"
HidD_GetProductString: "Tview"
HidP_GetCaps: 
  Usage 1
  UsagePage ff00
  InputReportByteLength 61
  OutputReportByteLength 61
  FeatureReportByteLength 0
  NumberLinkCollectionNodes 1
  NumberInputButtonCaps 0
  NumberInputValueCaps 2
  NumberInputDataIndices 2
  NumberOutputButtonCaps 0
  NumberOutputValueCaps 2
  NumberOutputDataIndices 2
  NumberFeatureButtonCaps 0
  NumberFeatureValueCaps 0
  NumberFeatureDataIndices 0

```

It turns out that the exchange is conducted in blocks of 61 bytes maximum, and there are 2 InputValue and 2 OutputValue interfaces. The function `HidP_GetValueCaps` returns more detailed information on them:

```text
HidP_GetValueCaps(HidP_Input):
    UsagePage ff00
    ReportID fe
    LinkUsage 1
    LinkUsagePage ff00
    BitSize 8
    ReportCount 8

    UsagePage ff00
    ReportID 1
    LinkUsage 1
    LinkUsagePage ff00
    BitSize 8
    ReportCount 60

HidP_GetValueCaps(HidP_Output):
    UsagePage ff00
    ReportID fd
    LinkUsage 1
    LinkUsagePage ff00
    BitSize 8
    ReportCount 8

    UsagePage ff00
    ReportID 2
    LinkUsage 1
    LinkUsagePage ff00
    BitSize 8
    ReportCount 60

```

From this data, the most interesting parts are `ReportID` — the ID of the report (essentially, the data packet) and `ReportCount` — its size. Data can be sent and received using the functions `HidD_SetOutputReport` and `HidD_GetInputReport` respectively.

After experimenting with these functions using different ReportIDs and data sizes, I was unable to achieve successful communication. After sniffing the USB traffic with **[USBPcap](https://desowin.org/usbpcap/)**, I discovered that data wasn't even attempting to be transmitted. A suspicion arose that this was some kind of "incorrect" HID.


<img width="585" height="96" alt="image" src="https://github.com/user-attachments/assets/224e9210-b880-4a52-b8c9-2ad90df22a3a" />


`SET_REPORT Request` remained unanswered.

## Reverse Engineering the ZaZaRemote Application

In the APK file of this application, I discovered the library `libtiqiaa_dev_usb.so`. It exports the following functions:

* `Java_com_icontrol_dev_TiqiaaUsbController_usbOpen`
* `Java_com_icontrol_dev_TiqiaaUsbController_usbClose`
* `Java_com_icontrol_dev_TiqiaaUsbController_usbSendCmd`
* `Java_com_icontrol_dev_TiqiaaUsbController_usbSendIR`
* `Java_com_icontrol_dev_TiqiaaUsbController_d`

Judging by the names, these implement the communication with the device. In their code, fragments resembling virtual function calls are frequently encountered:

```assembly
LDR R3, [R0]
LDR R3, [R3,#0x18]
BLX R3

```

Register `R0` is the first argument of this function. These functions are called only from the Java code `classes.dex`. Decompiling this file gives us their type:

```java
private native boolean usbOpen(Context context);
private native void usbClose();
private native boolean usbSendCmd(UsbDeviceConnection usbdeviceconnection, UsbEndpoint usbendpoint, int j, int k);
private native boolean usbSendIR(Context context, UsbDeviceConnection usbdeviceconnection, UsbEndpoint usbendpoint, int j, byte abyte0[], int k);
private native IControlIRData d(byte abyte0[]);

```

The Java code turned out to be obfuscated, however, some names were preserved. Regarding this library, the obfuscator only ruined the name of the last function (`d`), however, the names in the main Java code were almost all ruined.

After studying the decompiled Java code a bit, I found the following strings:

```java
com.tiqiaa.icontrol.e.i.a("DeviceHolder", (new StringBuilder("send......cmdType=")).append(i1).append(",cmdId=").append(j1).toString());
boolean flag1 = a.b(i1, j1);
com.tiqiaa.icontrol.e.i.d("DeviceHolder", (new StringBuilder("send....................freq=")).append(i1).append(",cmdId=").append(j1).append(",buffer.length=").append(abyte0.length).append(" , device = ").append(a).toString());
boolean flag1 = a.a(i1, abyte0, j1);

```

Debug logs are a reverse engineer's best friend.

To call native methods from Java code, the [JNI](https://en.wikipedia.org/wiki/Java_Native_Interface) (Java Native Interface) mechanism is used. The exported function must have the form:

```c
extern "C" JNIEXPORT void JNICALL Java_ClassName_MethodName(JNIEnv *env, jobject obj, <java arguments>)

```

Now we can define the function types in IDA:

```c
bool __cdecl Java_com_icontrol_dev_TiqiaaUsbController_usbOpen(JNIEnv *env, jobject obj, struct Context *context);
void __cdecl Java_com_icontrol_dev_TiqiaaUsbController_usbClose(JNIEnv *env, jobject obj);
bool __cdecl Java_com_icontrol_dev_TiqiaaUsbController_usbSendCmd(JNIEnv *env, jobject obj, struct UsbDeviceConnection *usbdeviceconnection, struct UsbEndpoint *usbendpoint, int cmdType, int cmdId);
bool __cdecl Java_com_icontrol_dev_TiqiaaUsbController_usbSendIR(JNIEnv *env, jobject obj, struct Context *context, struct UsbDeviceConnection *usbdeviceconnection, struct UsbEndpoint *usbendpoint, int freq, jbyte buffer, int cmdId);
struct IControlIRData *__cdecl Java_com_icontrol_dev_TiqiaaUsbController_d(JNIEnv *env, jobject obj, jbyteArray buffer);

```

Now the HexRays decompiler recognizes the JNI calls and the code becomes much more understandable. For example, the call mentioned above decompiles as:

```c
v5 = ((int (*)(void))(*env)->FindClass)();

```

### Decompilation Result of `usbSendCmd`

```c
bool __cdecl Java_com_icontrol_dev_TiqiaaUsbController_usbSendCmd(JNIEnv *env, jobject obj, struct UsbDeviceConnection *usbdeviceconnection, struct UsbEndpoint *usbendpoint, int cmdType, int cmdId)
{
  char v6; // r5@5
  bool result; // r0@12
  char data[24]; // [sp+8h] [bp-18h]@12
 
  dword_B57C = 0;
  if ( UsbEndpoint_bulkTransfer )
  {
    if ( usbdeviceconnection )
    {
      if ( usbendpoint )
      {
        switch ( cmdType )
        {
          case 0:
            v6 = 'L';
            goto LABEL_12;
          case 2:
            v6 = 'R';
            goto LABEL_12;
          case 3:
            v6 = 'H';
            goto LABEL_12;
          case 4:
            v6 = 'O';
            goto LABEL_12;
          case 6:
            v6 = 'C';
            goto LABEL_12;
          case 7:
            v6 = 'V';
            goto LABEL_12;
          case 1:
            v6 = 'S';
LABEL_12:
            data[0] = 'S';
            data[1] = 'T';
            data[3] = v6;
            data[2] = cmdId;
            data[4] = 'E';
            data[5] = 'N';
            result = sub_3528(env, usbdeviceconnection, usbendpoint, data, 6);
            break;
          default:
            result = 0;
            break;
        }
      }
      else
      {
        result = 0;
      }
    }
    else
    {
      result = 0;
    }
  }
  else
  {
    result = UsbEndpoint_bulkTransfer;
  }
  return result;
}

```

The code is elementary, the message format is obvious: it starts with the signature "ST", followed by the command type byte — one of the characters `{'L', 'R', 'H', 'O', 'C', 'V', 'S'}`, followed by the `cmdId` byte (simply an incremental identifier to match the command and the response), and everything ends with the signature "EN". The formed message is sent by the function `sub_3528`.

### Code of Function `sub_3528`

```c
int __cdecl sub_3528(JNIEnv *env, struct UsbDeviceConnection *usbdeviceconnection, struct UsbEndpoint *usbendpoint, void *data, int size)
{
  JNIEnv v5; // r1@1
  JNIEnv *v6; // r4@1
  int result; // r0@2
  int v8; // r2@3
  int tsize; // r7@5
  size_t fragmSize; // r5@9
  int v11; // r0@11
  JNIEnv v12; // r3@11
  int v13; // r6@11
  int rdOffs; // [sp+10h] [bp-80h]@7
  int v15; // [sp+14h] [bp-7Ch]@15
  int jbyteArray; // [sp+18h] [bp-78h]@1
  int fragmCnt; // [sp+1Ch] [bp-74h]@7
  char *_data; // [sp+28h] [bp-68h]@1
  char buf[64]; // [sp+34h] [bp-5Ch]@7
  int _stack_chk_guard; // [sp+74h] [bp-1Ch]@1
 
  _data = (char *)data;
  v5 = *env;
  v6 = env;
  _stack_chk_guard = ::_stack_chk_guard;
  jbyteArray = ((int (*)(void))v5->NewByteArray)();
  if ( jbyteArray )
  {
    v8 = UsbPackCounter + 1;
    if ( UsbPackCounter + 1 > 15 )
      v8 = 1;
    tsize = size;
    UsbPackCounter = v8;
    if ( size > 1024 )
      tsize = 1024;
    j_j_memset(buf, 0, 0x40u);
    buf[0] = 2;
    buf[3] = (tsize / 56 & 0x7F) + ((((tsize + -56 * (tsize / 56 & 0x7F)) >> 31) - (tsize + -56 * (tsize / 56 & 0x7Fu))) >> 31);
    rdOffs = 0;
    fragmCnt = 0;
    buf[2] = UsbPackCounter;
    while ( 1 )
    {
      if ( rdOffs >= tsize )
        goto LABEL_25;
      fragmCnt = (fragmCnt + 1) & 0xFF;
      fragmSize = tsize - rdOffs;
      if ( tsize - rdOffs > 56 )
        fragmSize = 56;
      buf[1] = fragmSize + 3;
      buf[4] = fragmCnt;
      j_j_memcpy(&buf[5], &_data[rdOffs], fragmSize);
      ((void (__fastcall *)(JNIEnv *, int, _DWORD, signed int))(*v6)->SetByteArrayRegion)(v6, jbyteArray, 0, 61);
      v11 = ((int (__fastcall *)(JNIEnv *))(*v6)->ExceptionCheck)(v6);
      v12 = *v6;
      v13 = v11;
      if ( v11 )
      {
        ((void (__fastcall *)(JNIEnv *))v12->ExceptionClear)(v6);
        v13 = 0;
        goto return_r6_del;
      }
      if ( !dword_B2A4 )
      {
LABEL_25:
        v13 = 1;
        goto return_r6_del;
      }
      v15 = ((int (__fastcall *)(JNIEnv *))v12->CallIntMethod)(v6);
      if ( ((int (__fastcall *)(JNIEnv *))(*v6)->ExceptionCheck)(v6) )
      {
        ((void (__fastcall *)(JNIEnv *))(*v6)->ExceptionClear)(v6);
        goto return_r6_del;
      }
      if ( v15 < 0 )
        break;
      rdOffs += fragmSize;
    }
    v13 = 0;
return_r6_del:
    ((void (__fastcall *)(JNIEnv *, int))(*v6)->DeleteLocalRef)(v6, jbyteArray);
    result = v13;
  }
  else
  {
    ((void (__fastcall *)(JNIEnv *))(*v6)->ExceptionClear)(v6);
    result = 0;
  }
  if ( _stack_chk_guard != ::_stack_chk_guard )
    j_j___stack_chk_fail(result);
  return result;
}

```

This function is a bit more complicated. It is visible that the maximum length of the sent message is limited to 1024 bytes. The message is divided into fragments. A fragment consists of a 5-byte header and a maximum of 56 bytes of data — totaling 61 bytes.

**Header Structure:**

* `buf[0] = 2` — constant. Remember ReportID 2? Looks like this is it. And ReportCount 60 — this is the size of the remaining data — also matches.
* `buf[1] = fragmSize + 3` — size of fragment data + 3, i.e., the size is calculated from the byte following this variable.
* `buf[2] = UsbPackCounter` — simply a counter, 1..15.
* `buf[3]`, calculated by a convoluted expression, is simply the number of fragments, which can be rewritten as:
```c
buf[3] = tsize / 56;
if (tsize % 56) buf[3]++;

```


* `buf[4] = fragmCnt` — fragment number, 1..buf[3].

The formed fragments are sent via a `CallIntMethod` call. It has the following type:
`jint (JNICALL *CallIntMethod)(JNIEnv *env, jobject obj, jmethodID methodID, ...);`

It is visible that HexRays failed this time — in the arguments there is only `v6 = JNIEnv *env`. However, in the assembly code, everything is in place:
`LDR R2, [R2,#(dword_B2A4 - 0xB284)] ; jmethodID methodID`

`methodID` is stored in the variable `dword_B2A4`. Let's see where it came from:
The write occurs in the functions `usbOpen` and `usbClose`. Obviously, we are interested in `usbOpen`.
<img width="719" height="138" alt="image" src="https://github.com/user-attachments/assets/9203da85-3734-4f22-a08f-790ca40c8b77" />


**Relevant Fragment:**

```c
v27 = ((int (__fastcall *)(JNIEnv *, int, const char *, const char *))(*v4)->GetMethodID)(
        v4,
        v26,
        "bulkTransfer",
        "(Landroid/hardware/usb/UsbEndpoint;[BII)I");
dword_B2A4 = v27;

```

So, that's the `UsbEndpoint::bulkTransfer` method. And nothing HID-related!

Now let's consider the device from the perspective of standard USB requests.

It's quite large, but the section that generates the command message is quite clear.

**Fragment of the usbSendIR function**

```
  buf[0] = 'S';
  buf[1] = 'T';
  buf[2] = cmdId;
  buf[3] = 'D';
  if ( freq > 255 )
  {
    LOBYTE(v36) = 0;
    v37 = -1;
    v38 = 0;
    while ( 1 )
    {
      v39 = (freq - IrFreqTable[v38] + ((freq - IrFreqTable[v38]) >> 31)) ^ ((freq - IrFreqTable[v38]) >> 31);
      if ( v37 != -1 && v39 >= v37 )
      {
        v39 = v37;
      }
      else
      {
        LOBYTE(v36) = v38;
        if ( !v39 )
          break;
      }
      if ( ++v38 == 30 )
        break;
      v37 = v39;
    }
  }
  else
  {
    v36 = (unsigned int)(freq - 1) <= 0x1C ? freq : 0;
  }
  buf[4] = v36;
  v40 = &buf[v22];
  v40[5] = 'E';
  v40[6] = 'N';
```
As with the other commands, it all starts with "ST," followed by the cmdId and the command code 'D', followed by a byte specifying the frequency. If the freq argument is greater than 255, it is looked up in the IrFreqTable frequency table; otherwise, it is copied directly. Then comes the data, and it all ends with "EN."

The function with the obfuscated name "d" turned out to be a parser for the received data.



If you look at the descriptor, you can see `Endpoint 1 Descriptor`:

* `bEndpointAddress: 0x81 (Input)`
* `bmAttributes: 0x03 (Interrupt)`

And `Endpoint 2 Descriptor`:

* `bEndpointAddress: 0x02 (Output)`
* `bmAttributes: 0x03 (Interrupt)`

The Android API `UsbEndpoint::bulkTransfer` sends data via `ioctl(fd, USBDEVFS_BULK, &ctrl)`. In the kernel driver, this corresponds to the function `proc_bulk`. However, it supports both Bulk and Interrupt endpoints.

Thus, this device is simply pretending to be HID to use the standard system driver, but in reality, it does not use the HID protocol.

Since I am writing the program for Windows, I have two options:

1. Write a specific driver (e.g., using libusb).
2. Try to work via the system HID driver.

I decided to start with the second option. The system driver provides the function `HidD_SetOutputReport`. It sends a `SET_REPORT` request to the Control Endpoint. This is not suitable for us. However, there is the function `WriteFile`. If you call it on an HID device, the data will be sent to the interrupt endpoint! This is exactly what we need.

I wrote a program that searches for the device, opens it, and sends the packet `02 09 01 01 01 53 54 17 56 45 4e` (Version request).
The response is read using `ReadFile`.

**Result:**

```text
30 30 30 30 30 30 30 31 09 00-000000000001.
0070 45 4e ff ff ff df ff f9 ef ff df ff bf fb ff EN.............

```

The format of the response is similar to the format of the request — the header is the same 5 bytes.
`53 54 17 56 30 01 ... 45 4E` -> `ST . V 0 . ... EN`
Version 0? Okay.

It turns out that the device has problems with the size of the data for sending — besides the response, all sorts of garbage pours in — usually what remains from the previous transmission.

Study of the dump and subsequent experiments allowed determining the functions of all commands:

* **'V' — Version** — request version — my device outputs a null GUID;
* **'L' — IdleMode** — standby mode — the device is in this mode after power is applied, or transitions to it by this command;
* **'S' — SendMode** — transmission mode — used for sending IR signals;
* **'R' — RecvMode** — reception mode — used for receiving IR signals;
* **'D' — Data** — in transmission mode — data for transmission, in reception mode — data of the captured IR packet;
* **'O' — Output** — in transmission mode — confirmation of transmission, in reception mode — request to capture/output data;
* **'C' — Cancel** — in reception mode — cancellation of reception, previously requested by 'O';
* **'H' — Unknown** — response to an unknown command.

### Changing the driver and working via bulkTransfer

After studying the HID API, I discovered that it doesn't support bulkTransfer at all, meaning I'll have to change the driver. The [WinUsb](https://docs.microsoft.com/en-us/windows/win32/api/winusb/) driver is suitable for working with this device.
After writing an INF file, I changed the driver to WinUsb and tried sending commands. Everything worked, and I received a response from the device—in response to sending commands (via `WinUsb_WritePipe`), I received a response in a similar format.

**Exchange dump with ZaZaRemote**

Despite previous successes, I still couldn't achieve the main goal—getting the device to transmit IR commands. The application was too large and complex, so I simply wanted to dump the USB traffic. But how could I do that with an Android application? The solution was found in the form of Android-x86 on VirtualBox. Although x86 isn't ARM, it still allows you to run native ARM binaries via NativeBridge. After installing and configuring the necessary software, I was able to get this application running in VirtualBox.

After launching the app and setting up USB forwarding, I was able to sniff USB traffic. This yielded a sequence of commands for initializing the reception and transmission of IR commands, as well as samples of IR data.

It turned out that the device was capable of not only transmitting but also receiving IR commands, but reception was rather poor—at a distance of 10 cm, and then only intermittently.

```text
- Transmission:

OUT:
0040 02 09 01 01 01 53 54 12 56 45 4e .....ST.VEN

IN:
0040 01 30 07 01 01 53 54 12 56 30 01 30 30 30 30 30 .0...ST.V0.00000
0050 30 30 30 2d 30 30 30 30 2d 30 30 30 30 2d 30 30 000-0000-0000-00
0060 30 30 2d 30 30 30 30 30 30 30 30 30 30 30 31 09 00-000000000001.
0070 45 4e ff ff ff df ff f9 ef ff df ff bf fb ff EN.............

OUT:
0040 02 09 02 01 01 53 54 13 53 45 4e .....ST.SEN

IN:
0040 01 0a 08 01 01 53 54 13 53 09 45 4e 30 30 30 30 .....ST.S.EN0000
0050 30 30 30 2d 30 30 30 30 2d 30 30 30 30 2d 30 30 000-0000-0000-00
0060 30 30 2d 30 30 30 30 30 30 30 30 30 30 30 31 09 00-000000000001.
0070 45 4e ff ff ff df ff f9 ef ff df ff bf fb ff EN.............

OUT:
0040 02 3b 03 02 01 53 54 14 44 00 ff ff ff ff b7 7f .;...ST.D.......
0050 7f 1b a3 23 a3 23 a3 69 a3 23 a3 23 a3 23 a3 23 ...#.#.i.#.#.#.#
0060 a3 23 a3 69 a3 69 a3 23 a3 69 a3 69 a3 69 a3 69 .#.i.i.#.i.i.i.i
0070 a3 69 a3 69 a3 23 a3 23 a3 23 a3 69 a3 .i.i.#.#.#.i.

OUT:
0040 02 2f 03 02 02 23 a3 23 a3 23 a3 23 a3 69 a3 69 ./...#.#.#.#.i.i
0050 a3 69 a3 23 a3 69 a3 69 a3 69 a3 7f 7f 7f 7f 7f .i.#.i.i.i......
0060 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 57 45 ..............WE
0070 4e N

IN:
0040 01 0a 09 01 01 53 54 14 4f 09 45 4e 30 30 30 30 .....ST.O.EN0000
0050 30 30 30 2d 30 30 30 30 2d 30 30 30 30 2d 30 30 000-0000-0000-00
0060 30 30 2d 30 30 30 30 30 30 30 30 30 30 30 31 09 00-000000000001.
0070 45 4e ff ff ff df ff f9 ef ff df ff bf fb ff EN.............

- Reception:

OUT:
0040 02 09 01 01 01 53 54 17 56 45 4e .....ST.VEN

IN:
0040 01 30 0c 01 01 53 54 17 56 30 01 30 30 30 30 30 .0...ST.V0.00000
0050 30 30 30 2d 30 30 30 30 2d 30 30 30 30 2d 30 30 000-0000-0000-00
0060 30 30 2d 30 30 30 30 30 30 30 30 30 30 30 31 09 00-000000000001.
0070 45 4e ff ff ff df ff f9 ef ff df ff bf fb ff EN.............

OUT:
0040 02 09 02 01 01 53 54 18 53 45 4e .....ST.SEN

0040 01 0a 0d 01 01 53 54 18 53 09 45 4e 30 30 30 30 .....ST.S.EN0000
0050 30 30 30 2d 30 30 30 30 2d 30 30 30 30 2d 30 30 000-0000-0000-00
0060 30 30 2d 30 30 30 30 30 30 30 30 30 30 30 31 09 00-000000000001.
0070 45 4e ff ff ff df ff f9 ef ff df ff bf fb ff EN.............

OUT:
0040 02 09 03 01 01 53 54 19 52 45 4e .....ST.REN

0040 01 0a 0e 01 01 53 54 19 52 13 45 4e 30 30 30 30 .....ST.R.EN0000
0050 30 30 30 2d 30 30 30 30 2d 30 30 30 30 2d 30 30 000-0000-0000-00
0060 30 30 2d 30 30 30 30 30 30 30 30 30 30 30 31 09 00-000000000001.
0070 45 4e ff ff ff df ff f9 ef ff df ff bf fb ff EN.............

OUT:
0040 02 09 04 01 01 53 54 1a 43 45 4e .....ST.CEN

IN:
0040 01 0a 0f 01 01 53 54 1a 43 13 45 4e 30 30 30 30 .....ST.C.EN0000
0050 30 30 30 2d 30 30 30 30 2d 30 30 30 30 2d 30 30 000-0000-0000-00
0060 30 30 2d 30 30 30 30 30 30 30 30 30 30 30 31 09 00-000000000001.
0070 45 4e ff ff ff df ff f9 ef ff df ff bf fb ff EN.............

OUT:
0040 02 09 05 01 01 53 54 1b 4f 45 4e .....ST.OEN

IN:
0040 01 3b 01 0e 01 53 54 00 44 ff ff ff ff ba 7f 7f .;...ST.D.......
0050 19 a4 21 a4 21 a4 68 a4 22 a4 21 a4 22 a4 22 a4 ..!.!.h.".!.".".
0060 22 a4 68 a4 68 a4 21 a4 68 a4 68 a4 68 a4 68 a4 ".h.h.!.h.h.h.h.
0070 68 a4 68 a4 22 a4 22 a4 22 a4 68 a4 22 fb ff h.h.".".".h."..

.....

0040 01 2f 01 0e 0e 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f ./..............
0050 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f ................
0060 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 7f 3e 13 45 .............>.E
0070 4e 82 02 82 02 82 7f 7f 7f 7f 7f 7f 7f fb ff N..............

```

Despite previous successes, I still couldn't achieve the main goal—getting the device to transmit IR commands. The application was too large and complex, so I simply wanted to dump the USB traffic. But how could I do that with an Android application? The solution was found in the form of Android-x86 on VirtualBox. Although x86 isn't ARM, it still allows you to run native ARM binaries via NativeBridge. After installing and configuring the necessary software, I was able to get this application running in VirtualBox.
The permissions requested definitely give credibility to this software.
<img width="463" height="467" alt="image" src="https://github.com/user-attachments/assets/51586e49-4e7d-497d-b5e0-71dbef5f43eb" />


Now let's look at how IR codes are transmitted—the `usbSendIR` function.

It's quite large, but the section that generates the command message is quite clear.

**Fragment of the usbSendIR function**

```c
  buf[0] = 'S';
  buf[1] = 'T';
  buf[2] = cmdId;
  buf[3] = 'D';
  if ( freq > 255 )
  {
    LOBYTE(v36) = 0;
    v37 = -1;
    v38 = 0;
    while ( 1 )
    {
      v39 = (freq - IrFreqTable[v38] + ((freq - IrFreqTable[v38]) >> 31)) ^ ((freq - IrFreqTable[v38]) >> 31);
      if ( v37 != -1 && v39 >= v37 )
      {
        v39 = v37;
      }
      else
      {
        LOBYTE(v36) = v38;
        if ( !v39 )
          break;
      }
      if ( ++v38 == 30 )
        break;
      v37 = v39;
    }
  }
  else
  {
    v36 = (unsigned int)(freq - 1) <= 0x1C ? freq : 0;
  }
  buf[4] = v36;
  v40 = &buf[v22];
  v40[5] = 'E';
  v40[6] = 'N';

```

As with the other commands, it all starts with "ST," followed by the `cmdId` and the command code 'D', followed by a byte specifying the frequency. If the `freq` argument is greater than 255, it is looked up in the `IrFreqTable` frequency table; otherwise, it is copied directly. Then comes the data, and it all ends with "EN."

The function with the obfuscated name "d" turned out to be a parser for the received data.

## Researching the IR Packet Format

Having received a dump of control commands and IR packets, I was able to implement full control of the device — receiving and transmitting IR signals. However, in order to synthesize an arbitrary IR signal, it was necessary to determine the format in which it is encoded. For this, I connected an IR photoreceiver to an oscilloscope and began investigating the sent signals.

Through experiments, I found out the encoding format: the **most significant bit** of each byte determines whether the transmitter is on or not, and the **lower 7 bits** — the time.
**The unit of time turned out to be equal to 16 µsec.**

**Example:**
`8A` — transmitter is on for 160 µsec;
`8A 05 FF 83` — 160 µsec on, pause 80 µsec, 2.08 msec on.

When the transmitter is on, the LED pulses at a frequency of **~36.64 kHz**. Theoretically, this frequency should be determined by the `freq` argument of the `usbSendIR` command, but experiments showed that the device absolutely does not react to this argument. Nevertheless, the household appliances I have normally received the signals from this transceiver.

The format of the data recorded by the device in reception mode turned out to be similar.

## TiqiaaUsbIr Class and IR Control Program

I implemented control of the transceiver in the form of a C++ class `TiqiaaUsbIr` and wrote a simple program `CaptureIR` in Qt. Besides the functions of receiving and transmitting IR signals, I implemented the synthesis and decoding of signals using the **NEC protocol**. This protocol is used, for example, in LG TV remotes. I also implemented saving and loading IR signals in the raw format and **LIRC** format. There was an idea to make a module for WinLirc, but there turned out to be a crooked and not fully implemented API, so I postponed this idea for now.

The sources and compiled program can be downloaded [here](https://gitlab.com/XenRE/tiqiaa-usb-ir).

**Example usage of the TiqiaaUsbIr class:**

```cpp
std::vector<std::string> IrDev;
TiqiaaUsbIr::EnumDevices(IrDev); // Get list of devices
TiqiaaUsbIr Ir;
Ir.Open(IrDev[0].c_str()); // Open the first device
Ir.SendNecSignal(0x0408); // Send IR code (LG POWER)
Ir.Close();

```

**Captured Power On signal:**


<img width="510" height="173" alt="image" src="https://github.com/user-attachments/assets/00e12552-6502-47ab-84e1-cf0e3accb778" />


**The same, synthesized:**


<img width="510" height="173" alt="image" src="https://github.com/user-attachments/assets/89129434-5521-413e-9443-bc6686de01b7" />


**In the process of capture, something went wrong:**


<img width="510" height="172" alt="image" src="https://github.com/user-attachments/assets/0130b518-8b02-4106-a164-fd80797c5ce7" />


## Summary

In the process of research, the USB protocol of the **Tiqiaa Tview** IR transceiver was fully restored, and a driver INF file and software for working with it were written.

The examined IR transceiver is a very cheap, accessible, and compact ($5 on Ali, dimensions 15 x 10 x 5 mm) device for controlling household appliances and researching their IR protocols. Unfortunately, the transmitter frequency control turned out to be non-functional, which in my case did not cause problems, however, it is possible that there is equipment with more fastidious receivers.

The reception mode, due to the meager radius and low reliability of capture, is unsuitable for use as a full-fledged IR receiver — the record range of successful capture is ~30 cm, while the remote must be aimed exactly at the receiver, and even point-blank, not all sent signals are captured normally. Nevertheless, it is useful for capturing signals and researching IR remote protocols.

## Bonus

Interesting IR codes for LG televisions:

* **POWER** `0408`
* **POWERON** `04C4`
* **POWEROFF** `04C5`
* **IN_STOP** `04FA`
* **IN_START** `04FB`
* **POWERONLY** `04FE`
* **EZ_ADJUST** `04FF`

P.S. I am looking for information about **LG AccessUSB**. More details [here](http://webos-forums.ru/topic5964.html)
