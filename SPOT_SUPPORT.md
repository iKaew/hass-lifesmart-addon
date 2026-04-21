# SPOT Device Support

## Overview

SPOT devices in the LifeSmart ecosystem can provide three different roles in Home Assistant:

1. **Light entity** - Controls RGB/RGBW lighting functions on supported SPOT models
2. **Remote entity** - Sends learned or raw IR commands
3. **Climate entity** - Controls an air conditioner through a LifeSmart A/C IR profile

The climate entity is optional and must be configured through the integration options flow.

## Supported SPOT Devices

| Device Type | Description | Light Control | IR Remote Control |
|-------------|-------------|---------------|-------------------|
| SL_SPOT | LifeSmart SPOT device | ✓ RGB/RGBW | ✓ IR Learning/Sending |
| MSL_IRCTL | LifeSmart IR controller | - | ✓ IR Sending |
| OD_WE_IRCTL | LifeSmart IR controller | - | ✓ IR Sending |

For A/C climate support, the integration currently treats these SPOT-family IR devices as candidates:
- `SL_SPOT`
- `MSL_IRCTL`
- `OD_WE_IRCTL`

## Light Entity Features

The SPOT light entity supports:

- **RGB Color Control**: Full color spectrum control (0-255 for each RGB component)
- **Brightness Control**: Adjustable brightness levels
- **On/Off Control**: Standard light switching
- **Color Temperature**: If supported by the device
- **Effects**: Device-specific lighting effects

### Light Entity Usage

```yaml
# Turn on SPOT light with specific color
- service: light.turn_on
  target:
    entity_id: light.spot_device_light
  data:
    rgb_color: [255, 100, 50]  # Orange color
    brightness: 200

# Turn off SPOT light
- service: light.turn_off
  target:
    entity_id: light.spot_device_light
```

## Remote Entity Features

The SPOT remote entity supports:

- **IR Code Learning**: Store named IR codes locally in Home Assistant
- **IR Code Sending**: Send learned or predefined IR codes
- **Multiple Device Support**: Control multiple IR devices from one SPOT
- **Command Storage**: Store learned commands for reuse

### Remote Entity Usage

```yaml
# Send a learned IR command
- service: remote.send_command
  target:
    entity_id: remote.spot_device_remote
  data:
    command: "power_toggle"

# Send raw IR data directly
- service: remote.send_command
  target:
    entity_id: remote.spot_device_remote
  data:
    command: "018B4F0538016F4F3E57FF57FF7FFDD554FF0001AD8B0360014F6F0340C2"

# Save a new local IR command
- service: remote.learn_command
  target:
    entity_id: remote.spot_device_remote
  data:
    command: "volume_up"
    device: "tv_remote"
    command_type: "018B4F0538016F4F3E57FF57FF7FFDD554FF0001AD8B0360014F6F0340C2"

# Alternative local save format
- service: remote.learn_command
  target:
    entity_id: remote.spot_device_remote
  data:
    command:
      - "volume_down"
      - "018B4F0538016F4F3E57FF57FF7FFDD554FF0001AD8B0360014F6F0340C2"
    device: "tv_remote"
```

## Device Configuration

SPOT devices are automatically discovered and configured when the LifeSmart integration is set up. No additional configuration is required.

### Entity Naming Convention

- **Light Entity**: `{device_name} Light`
- **Remote Entity**: `{device_name} Remote`

For example, a SPOT device named "Living Room SPOT" will create:
- `light.living_room_spot_light`
- `remote.living_room_spot_remote`

## Local IR Command Storage

The LifeSmart cloud API used by this integration sends IR data but does not expose a
physical IR capture endpoint. The `remote.learn_command` service therefore stores the IR
payload you provide in Home Assistant local storage. Later, `remote.send_command` will
look up the saved command name and send the stored IR data through the SPOT device.

## Base64 IR Code Support

The SPOT remote entity supports sending IR codes that are encoded in Base64 format. This is useful when:

- IR codes are stored or transmitted as Base64 strings
- Working with raw IR data from other systems
- Importing IR codes from external databases

### Base64 IR Code Format

```yaml
# Send Base64 encoded IR code
- service: remote.send_command
  target:
    entity_id: remote.spot_device_remote
  data:
    command: "UHJvdG9jb2w6IE5FQyA2NDAgS0h6"  # Example Base64 IR code
```

Saved and raw commands are sent to LifeSmart as provided.

## A/C Climate Entity

When a SPOT device is configured with an A/C brand/profile, the integration creates a Home Assistant climate entity for that device.

### Supported A/C Controls

- Power on/off
- HVAC mode
- Target temperature
- Fan speed
- Swing mode

### Important Notes

- The SPOT device does not provide a built-in temperature sensor, so the climate entity does not expose `current_temperature`
- The entity restores its last Home Assistant state after reload, but this is still optimistic state restoration rather than a live temperature/state poll from the A/C
- A/C commands use the LifeSmart A/C IR profile APIs and then send the generated IR code through the SPOT device

## Configuring A/C Support

Use the integration options flow:

1. Open `Settings -> Devices & Services`
1. Select the `LifeSmart` integration
1. Choose `Configure`
1. Select `Configure SPOT A/C remote`
1. Choose the SPOT device
1. Use the brand search field to narrow the LifeSmart A/C brand list
1. Select the A/C brand
1. Select the remote profile
1. Save

The options flow also supports:
- Removing a configured SPOT A/C remote
- Prefilling brand/profile defaults from the current remote assignment returned by `GetRemoteList`

## A/C Debugging

If the LifeSmart app profile works but Home Assistant behavior differs, you can dump `GetACCodes` responses for a profile using:

```bash
python scripts/dump_ac_profile_codes.py \
  --brand "Mitsubishi Electric" \
  --idx 2997 \
  --keys power \
  --powers 0,1 \
  --modes 0-4 \
  --temps 16-30 \
  --winds 0-3 \
  --swings 0-4
```

This writes a JSON file under `config/` that helps identify which `GetACCodes` combinations produce `power_off`, `power_on`, or other useful IR variants for a profile.

## Troubleshooting

### Light Control Issues
- Ensure the SPOT device is properly connected to the LifeSmart hub
- Check that the device firmware is up to date
- Verify RGB values are within valid ranges (0-255)

### IR Remote Issues
- Ensure the SPOT device is positioned to receive IR signals clearly
- Check that the original remote uses standard IR frequencies (typically 38kHz)
- Verify that learned commands are stored correctly (check entity attributes)

### Common Problems
- **No remote entity created**: Ensure the device type is correctly identified as SL_SPOT
- **IR learning fails**: Try different distances and angles between remotes
- **Commands not working**: Verify the target device accepts the learned IR codes
- **A/C brand list is too long**: Use the brand search step in the options flow before selecting the brand
- **A/C turns on but not off**: Dump `GetACCodes` for the selected profile and compare the returned `power_off` combinations
- **A/C resets to defaults after reload**: Update to a version with restore-state support for the SPOT climate entity

## Technical Details

- **Platform**: Remote control uses the standard Home Assistant `remote` platform
- **IR Protocol**: Supports standard IR remote control protocols
- **Storage**: Learned IR codes are stored locally on the SPOT device
- **Communication**: All control goes through the LifeSmart Cloud API

## API Integration

The SPOT implementation uses the following LifeSmart API endpoints:

- `get_ir_remote_list_async()` - Retrieve available IR remote configurations
- `get_ir_remote_async()` - Get detailed IR remote information
- `send_ir_code_async()` - Send IR codes to control devices
- `get_ac_codes_async()` - Generate IR codes for A/C state changes
- `learn_ir_code_async()` - Learn new IR codes (future enhancement)

## Future Enhancements

- Enhanced IR learning interface with device type detection
- Support for additional IR protocols
- Bulk IR code management
- Integration with popular remote control databases</content>
<parameter name="filePath">/workspaces/hass-lifesmart-addon/SPOT_SUPPORT.md
