# Papouch PAPAGO checks for Checkmk

Extension of [zito/cmk-papouch-papago2theth](https://github.com/zito/cmk-papouch-papago2theth).
The original PAPAGO 2TH ETH plugin is preserved. Version **2.3.2** adds a separate
plugin for **PAPAGO TH 2DI DO ETH**, using Checkmk's Check API v2 (2.3.0 or later).

## New device services

| Service | Data |
| --- | --- |
| Temperature 1 | Temperature, with device status and Checkmk temperature thresholds |
| Humidity 2 | Relative humidity, with device status and Checkmk humidity thresholds |
| Dew point 3 | Dew point, with device status and Checkmk temperature thresholds |
| Digital input 1 / 2 | OFF/ON and converted cumulative counter, including configured unit |
| Relay output 1 | OFF/ON status |

Service suffixes are SNMP channel indexes. A temperature-only probe discovers
only its enabled quantities. Unused sensor types are excluded; configured
sensors with measurement errors remain visible. Status 1 (not yet measured) is
UNKNOWN, status 4 (measurement error) is CRIT, and device limit violations are
WARN. Invalid readings produce no measurement metrics.

Temperature and dew point support Celsius, Fahrenheit and Kelvin device units.
Humidity uses percent. Humidity defaults match upstream: upper WARN/CRIT
60/80%, lower WARN/CRIT 30/20%. Customize these through Checkmk's existing
temperature and humidity rules.

Digital ON and OFF both report OK: the correct alarm polarity depends on what
is wired to the input or relay. This release provides informational digital
states, without a contact-alarm ruleset. Unexpected digital codes report UNKNOWN.
The `papago_counter` metric records the converted cumulative reading, not a rate;
its arbitrary device-configured unit is shown in the service summary. A device
counter reset can make the graph fall. The plugin only reads SNMP data.

## Install

Copy `cmk-papouch-papago2theth-2.3.2.mkp` to your Checkmk server, then run as the
Checkmk site user:

```sh
mkp install /path/to/cmk-papouch-papago2theth-2.3.2.mkp
```

Alternatively, install both `.py` files from
`cmk_addons_plugins/papouch/agent_based/` into
`~/local/lib/python3/cmk_addons/plugins/papouch/agent_based/` in the site.

Enable SNMP on the PAPAGO. In Checkmk, configure the host for SNMP **v1** and the
device's read community, then run service discovery and activate changes.
The new model is detected by the presence of its input and output OIDs in
`.1.3.6.1.4.1.18248.34`. No particular firmware `sysDescr` spelling is required.

For command-line discovery and verification, as the site user:

```sh
cmk -vI PAPAGO_HOST
cmk -nv PAPAGO_HOST
```

## Build and test

```sh
python3 -m unittest -v test_papago_th2dido
python3 build_mkp.py
```

The tests exercise parsing, discovery, device status handling, units, counter
scaling, missing channels and model-specific OIDs using lightweight Checkmk API
doubles. They do **not** validate a full Checkmk installation. Live device and
Checkmk-site validation are still required before production use.

To collect diagnostic data on a machine with Net-SNMP installed:

```sh
snmpwalk -v1 -c 'YOUR_READ_COMMUNITY' -On PAPAGO_IP .1.3.6.1.4.1.18248.34
```

## Protocol references

- [Official PAPAGO TH 2DI DO ETH product page](https://en.papouch.com/papago-th-2di-do-eth-environment-monitor-p3159/)
- [Official MIB](https://cdn.en.papouch.com/data/user-content/old_eshop/files/PGO_TH2DIDO_E_1/papago-th-2di-do.zip), `PAPAGO-1TH-2DI-1DO-V02-MIB`
- [Official manual](https://cdn.en.papouch.com/data/user-content/products/PGO_TH2DIDO/papago-th-2di-do_manual_en.pdf), pages 25–28

The MIB confirms subtree 34 and the input, output and sensor table layout.
The manual's general-device OID examples contain subtree 31; the new plugin
does not rely on those examples. The MIB uses humidity unit code 0; code 3 is
also accepted because the manual's SNMP section lists it.

Original author: Václav Ovsík. License: GNU GPL version 3 or later; see the
original `README` for the upstream copyright and license notice.
