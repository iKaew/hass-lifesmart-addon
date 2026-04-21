LifeSmart integration for Home Assistant.

Current supported features:
- Switches
- Door lock status/information
- Smart plugs
- Sensors
- Motion sensors
- Water leakage sensors
- Curtain/cover devices
- SPOT light control
- SPOT IR remote control
- SPOT A/C climate control through LifeSmart A/C remote profiles
- Native A/C control panel climate entities
- Nature Series switch, temperature, and thermostat support

SPOT support currently includes:
- `SL_SPOT`
- `MSL_IRCTL`
- `OD_WE_IRCTL`

Native motion sensor support currently includes:
- `SL_SC_MHW`
- `SL_SC_BM`
- `SL_SC_CM`

Native water leakage sensor support currently includes:
- `SL_SC_WA` `WA` moisture alarm reporting
- `SL_SC_WA` `V` battery reporting

Native A/C control panel support currently includes:
- `V_AIR_P`
- `V_SZJSXR_P`
- `V_T8600_P`

Nature Series support currently includes:
- `SL_NATURE` switch-board variants
- `SL_NATURE` thermostat variants
- `SL_NATURE` `P4` temperature sensor reporting

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

Nature thermostat support currently provides:
- Automatic climate entity creation for thermostat variants
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
