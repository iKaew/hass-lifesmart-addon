LifeSmart integration for Home Assistant.

Current supported features:
- Switches
- Door lock status/information
- Smart plugs
- Sensors
- Motion sensors
- Curtain/cover devices
- SPOT light control
- SPOT IR remote control
- SPOT A/C climate control through LifeSmart A/C remote profiles
- Native A/C control panel climate entities

SPOT support currently includes:
- `SL_SPOT`
- `MSL_IRCTL`
- `OD_WE_IRCTL`

Native motion sensor support currently includes:
- `SL_SC_MHW`
- `SL_SC_BM`
- `SL_SC_CM`

Native A/C control panel support currently includes:
- `V_AIR_P`
- `V_SZJSXR_P`
- `V_T8600_P`

SPOT A/C support currently provides:
- Climate entity creation from the A/C remote already assigned in the LifeSmart app
- Power on/off
- HVAC mode
- Target temperature
- Fan speed
- Swing mode
- Removal of configured SPOT A/C remotes from the options flow
- Restore of last Home Assistant climate state after reload

Native A/C control panel support currently provides:
- Automatic climate entity creation from LifeSmart devices
- Power on/off
- HVAC mode
- Current temperature
- Target temperature
- Fan speed

Important notes:
- SPOT A/C entities do not expose `current_temperature`, because SPOT devices do not include a temperature sensor
- Native A/C control panel entities expose `current_temperature` when the device reports the `T` attribute
- All communication is cloud-based through the LifeSmart API and websocket updates
- There is no direct local LAN communication with the LifeSmart hub

Main setup/configuration capabilities:
- Standard integration setup through the Home Assistant UI
- SPOT A/C assignment through the integration options flow
- Use of the existing A/C remote assignment returned by LifeSmart `GetRemoteList`

Useful docs:
- [README.md](./README.md)
- [SPOT_SUPPORT.md](./SPOT_SUPPORT.md)
- [CURTAIN_SUPPORT.md](./CURTAIN_SUPPORT.md)

Issues and suggestions:
[https://github.com/iKaew/hass-lifesmart-addon/](https://github.com/iKaew/hass-lifesmart-addon/)
