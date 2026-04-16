LifeSmart integration for Home Assistant.

Current supported features:
- Switches
- Door lock status/information
- Smart plugs
- Sensors
- Curtain/cover devices
- SPOT light control
- SPOT IR remote control
- SPOT A/C climate control through LifeSmart A/C remote profiles

SPOT support currently includes:
- `SL_SPOT`
- `MSL_IRCTL`
- `OD_WE_IRCTL`

SPOT A/C support currently provides:
- Climate entity creation from the A/C remote already assigned in the LifeSmart app
- Power on/off
- HVAC mode
- Target temperature
- Fan speed
- Swing mode
- Removal of configured SPOT A/C remotes from the options flow
- Restore of last Home Assistant climate state after reload

Important notes:
- SPOT A/C entities do not expose `current_temperature`, because SPOT devices do not include a temperature sensor
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
