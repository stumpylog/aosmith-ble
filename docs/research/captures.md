# Captures

How to extract Android Bluetooth HCI logs, and an index of this project's captures. The files are not redistributed because they contain device-identifying values.

## Extracting an Android HCI snoop log

### Prerequisites

- An Android device with Developer Options enabled and USB debugging on
- ADB on your computer and a USB cable
- Wireshark to read the result

### Steps

1. In **Settings > System > Developer Options**, enable **Bluetooth HCI snoop log**, then toggle Bluetooth off and on (the setting location varies by Android version).
2. Connect to the heater, perform the operations to capture, disconnect, then turn the log off.
3. Generate a bug report, since the log lives in a protected location:

    ```bash
    adb bugreport bugreport.zip
    ```

    Some Android versions allow pulling the log directly with `adb pull /data/misc/bluetooth/logs/btsnoop_hci.log`.

4. Unzip the bug report and look for `btsnoop_hci.log` (current) or `btsnoop_hci.log.last` (the preceding session). On Android 9 and later the directory is `FS/data/misc/bluetooth/logs/`. Android 8 and below use `FS/data/log/bt/`.
5. Check the file is a valid capture. `file btsnoop_hci.log` should report "BTSnoop version 1, Unencapsulated HCI", and a file under 1 KB means nothing was captured.

### Analysing

Open the log in Wireshark. Useful display filters are `btatt` (ATT only), `btgatt` (GATT operations), `btle` (all BLE) and `bluetooth.addr == <device MAC>` for one device. To share a capture as text, use File > Export Packet Dissections > As Plain Text with "Packet details" checked, and anonymize device addresses first.

### Best practices

- Clear stale logs by disabling and re-enabling snooping before each session.
- Keep notes of what you did and when. Capture the same sequence more than once to separate fixed from variable data.
- Reduce other Bluetooth traffic during capture.

!!! warning "Bug reports are sensitive"
    A bug report contains Bluetooth MAC addresses, serial numbers or iCOMM identifiers, WiFi SSIDs and history, and the installed-app list. Sanitize before sharing. The advertised device name also embeds part of the unit's identity.

## Over-the-air capture (nRF sniffer)

An Android HCI log shows only what the phone did. For what is actually on the air, use an nRF52840 dongle running the Nordic BLE sniffer firmware and follow the heater's address; the air capture is the authoritative record.

Useful `tshark` filters after capture:

```bash
# What actually went out, by opcode
tshark -r air.pcap -Y btatt -T fields -e _ws.col.info | sed 's/,.*//' | sort | uniq -c

# Writes, responses and notifications only
tshark -r air.pcap -Y "btatt.opcode in {0x12 0x13 0x1b}" \
       -T fields -e frame.number -e btatt.handle -e btatt.value

# Did the central answer the device's MTU request?
tshark -r air.pcap -Y "btatt.opcode==0x02 || btatt.opcode==0x03" -T fields -e _ws.col.info
```

If `tshark` cannot read a pcap in a restricted directory, copy it to a plain temporary directory. The sniffer's live view is often filtered to ATT and SMP and hides advertising PDUs, though the pcap contains them.

## Capture index

| Capture | What it shows |
| --- | --- |
| `initial` | An Android log of the app talking to the heater. All modes were set, with no particular order, amount or days. Setpoint was 124F or 120F. |
| `setpoint/initial` | Setpoint varied 124F -> 120F -> 126F -> 124F, plus power usage and alert screens viewed. The app signed out partway, so it may include a second handshake. |
| `setpoint/stepwise` | Setpoint stepped from 114F up to 124F, then the app was switched to Celsius display and at least 47C was sent. The app was unstable in Celsius (stale display, crashes, sign-outs). |
| `toggling` and `new_toggling.pcap` | The heater was toggled repeatedly between Hybrid and Electric, first with Electric for 1 day, then 5 days. Setpoint was 124F. |
| `advertising.pcap` | An nRF sniffer capture of the heater advertising. See below. |
| `btsnoop_hci.log` | Raw HCI log with no description; not indexed. |

### Advertising result

The proprietary service UUID is **not** advertised (**verified on hardware**). `ADV_IND` carries only Flags and the device name (`iCOMM-AC000W037XXXXXX`). `SCAN_RSP` carries only manufacturer-specific data, company ID `0xFFFF`, with a value equal to the device's own MAC bytes. A client can discover the heater only by name prefix (`iCOMM-*`); a service-UUID scan filter is not viable.
