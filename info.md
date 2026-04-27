LifeSmart integration for Home Assistant.

Current supported features:
- Switches
- Door lock status/information
- Smart plugs
- Sensors
- Motion sensors
- Radar motion sensors
- CO2 sensors
- Environment sensors
- DEFED door/motion/siren/key fob sensors
- TVOC+CO2 environment sensors
- ELIQ electricity meters
- Air purifiers
- C100/C200 door locks
- HA interface and 485 controllers
- DLT electricity meters
- Noise sensors
- Smart alarm status
- Water leakage sensors
- Garage door covers
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
- `SL_P_IR`
- `SL_P_IR_V2`

Native motion sensor support currently includes:
- `SL_SC_MHW`
- `SL_SC_BM`
- `SL_SC_CM`

Native water leakage sensor support currently includes:
- `SL_SC_WA` `WA` moisture alarm reporting
- `SL_SC_WA` `V` battery reporting

Native CO2 sensor support currently includes:
- `SL_SC_CA` temperature, humidity, CO2, and battery reporting

Native environment sensor support currently includes:
- `SL_SC_THL` temperature, humidity, illuminance, and battery reporting
- `SL_SC_BE` temperature, humidity, illuminance, and battery reporting

Native TVOC+CO2 environment sensor support currently includes:
- `SL_SC_CQ` temperature, humidity, CO2, TVOC, battery, and USB supply voltage reporting

Native ELIQ electricity meter support currently includes:
- `ELIQ_EM` average power reporting

Native air purifier support currently includes:
- `OD_MFRESH_M8088` power control
- `OD_MFRESH_M8088` operating mode, temperature, humidity, PM2.5, filter life, and UV reporting

Native C100/C200 door lock support currently includes:
- `SL_LK_TY` battery, lock, alarm, and doorbell reporting
- `SL_LK_DJ` battery, lock, alarm, and doorbell reporting

Native controller support currently includes:
- `SL_JEMA` relay control and status input reporting
- `V_485_P` relay control and metering/environment/air-quality sensor reporting
- `V_DLT_645_P` / `V_DLT645_P` energy and power reporting

Native DEFED sensor support currently includes:
- `SL_DF_GG` door, external input, tamper, temperature, and battery reporting
- `SL_DF_MM` motion, tamper, temperature, and battery reporting
- `SL_DF_SR` siren, tamper, temperature, and battery reporting
- `SL_DF_BB` key fob button and battery reporting

Native noise sensor support currently includes:
- `SL_SC_CN` noise, alarm threshold, buzzer alarm, and correction reporting

Native smart alarm support currently includes:
- `SL_ALM` play and volume/silent state reporting

Native radar motion sensor support currently includes:
- `SL_P_RM` motion reporting

Native garage door support currently includes:
- `SL_ETDOOR` position cover reporting and open/close/stop/position control

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
