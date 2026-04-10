# LifeSmart Curtain Device Support

This document describes the comprehensive curtain device support implemented in the LifeSmart Home Assistant addon.

## Supported Curtain Device Types

The addon now supports the following LifeSmart curtain device types:

### Position-Based Curtain Devices

These devices support position control (0-100%) with full open/close/stop/set position capabilities:

- **SL_DOOYA** - Curtain (DuYa) motor
- **SL_DOOYA_V2** - Quick Link Curtain Motor
- **SL_DOOYA_V3** - Tubular Motor
- **SL_DOOYA_V4** - Tubular Motor (lithium battery)

**Capabilities:**
- Open to 100% (fully open)
- Close to 0% (fully closed)
- Stop mid-movement
- Set to specific position (0-100%)
- Position feedback

### Function-Based Curtain Devices

These devices support basic open/close/stop operations without position feedback:

- **SL_SW_WIN** - Curtain control switch
- **SL_CN_IF** - BLEND curtain controller
- **SL_CN_FE** - Gezhi/Sennathree-key curtain controller
- **SL_P_V2** - MINS curtain motor controller

**Capabilities:**
- Open curtain
- Close curtain
- Stop curtain movement

## Control Mechanism

The curtain devices use different control mechanisms based on their type:

### Position-Based Devices (SL_DOOYA family)

These devices use internal byte encoding for position control:

- **P1 Index**: Position feedback
  - Bit 7 (0x80): Direction indicator
    - 0x80 set: Opening
    - 0x80 clear: Closing
  - Bits 0-6 (0x7F): Position percentage (0-100%)

- **P2 Index**: Control port
  - Command: `type=0xCF, val=<position>` - Set to specific position (0-100)
  - Command: `type=0xCE, val=0x80` - Stop movement

### Function-Based Devices

These devices use simple on/off commands for each operation:

- **Open Action**: `type=0x81, val=1` on open index
- **Close Action**: `type=0x81, val=1` on close index
- **Stop Action**: `type=0x81, val=1` on stop index

Device-specific index mappings:
- **SL_SW_WIN**: OP (Open), CL (Close), ST (Stop)
- **SL_CN_IF**: P1 (Open), P3 (Close), P2 (Stop)
- **SL_CN_FE**: P1 (Open), P3 (Close), P2 (Stop)
- **SL_P_V2**: P2 (Open), P3 (Close), P4 (Stop)

## Home Assistant Integration

All curtain devices are automatically discovered and added to Home Assistant as `cover` entities.

### Entity Attributes

Each curtain entity has the following attributes:
- `agt`: Hub ID (internal)
- `me`: Device ID (internal)
- `devtype`: Device type identifier
- `current_position`: Current position (0-100) for position-based devices only

### Supported Services

The following Home Assistant cover services are supported:

#### Position-Based Devices

- `cover.open_cover` - Fully open the curtain
- `cover.close_cover` - Fully close the curtain
- `cover.stop_cover` - Stop the curtain movement
- `cover.set_cover_position` - Set curtain to specific position (0-100%)

Example YAML automation:
```yaml
automation:
  - alias: "Open curtains at sunrise"
    trigger:
      platform: sun
      event: sunrise
    action:
      - service: cover.open_cover
        target:
          entity_id: cover.sl_dooya_abc123_xyz
          
  - alias: "Set curtains to 50% at noon"
    trigger:
      platform: time
      at: "12:00:00"
    action:
      - service: cover.set_cover_position
        target:
          entity_id: cover.sl_dooya_abc123_xyz
        data:
          position: 50
```

#### Function-Based Devices

- `cover.open_cover` - Open the curtain
- `cover.close_cover` - Close the curtain
- `cover.stop_cover` - Stop the curtain movement

Example YAML automation:
```yaml
automation:
  - alias: "Open blinds when motion detected"
    trigger:
      platform: state
      entity_id: binary_sensor.motion_sensor
      to: "on"
    action:
      - service: cover.open_cover
        target:
          entity_id: cover.sl_cn_if_hub01_dev001
```

## Implementation Details

### API Commands

The implementation uses the LifeSmart Cloud Platform API's `EpSet` interface to control curtains:

```
POST /api/EpSet

Parameters:
- type: Command type (0xCF for position, 0xCE for stop, 0x81 for function)
- val: Command value (0-100 for position, 0x80 for stop, 1 for functions)
- idx: Index/port name (P1, P2, P3, etc.)
- agt: Hub/Gateway ID
- me: Device ID
```

### Websocket Updates

Position updates for position-based devices are received through the WebSocket connection and automatically update the Home Assistant entity state:

```json
{
  "type": "io",
  "msg": {
    "devtype": "SL_DOOYA",
    "agt": "hub_id",
    "me": "device_id",
    "idx": "P1",
    "type": 0x81,
    "val": 0x96          // 0x80 + 0x16 = Opening, 22% open
  }
}
```

## Troubleshooting

### Device Not Appearing

1. Ensure the LifeSmart API connection is successful (check logs)
2. Verify the device type is supported (in COVER_TYPES constant)
3. Check that the device is not in the exclude list
4. Restart Home Assistant to reload entities

### Position Not Updating

1. Check WebSocket connection is active
2. Verify device firmware supports position feedback
3. For function-based devices, position will not update automatically
4. Check LifeSmart API credentials and permissions

### Commands Not Working

1. Verify device is powered on and connected to hub
2. Check device ID and hub ID in logs
3. Ensure device supports the requested operation
4. Try manual control through LifeSmart app first

## Testing

To test curtain functionality:

1. **List all entities**:
   ```shell
   homeassistant/shell: ha core check
   ```

2. **Check cover state**:
   ```yaml
   Call Service > cover.set_cover_position
   Entity: cover.sl_dooya_...
   Data: { position: 50 }
   ```

3. **Monitor logs**:
   ```
   logger:
     default: info
     logs:
       custom_components.lifesmart: debug
   ```

## References

- LifeSmart Cloud Platform API: See `/docs/LifeSmart Cloud Platform API.pdf`
- Device Attributes: See `/docs/LifeSmart Device Attribute List.pdf`
- Section 2.3: Curtain Controller Series (Device Attribute List)
- Section 2.3.2: DOOYA Curtain Motor (Device Attribute List)
- Section 2.3.3: MINS Curtain Motor Controller (Device Attribute List)

## Future Enhancements

Planned improvements for curtain support:

- [ ] Add tilt control for curtains with tilt capability
- [ ] Implement position calibration for devices without feedback
- [ ] Add support for screen/blind devices (SL_DOOYA subvariants)
- [ ] Add cover group/scene support
- [ ] Implement position-based automations
- [ ] Add cover availability state tracking
