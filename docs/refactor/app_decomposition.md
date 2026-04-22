# `backend/app.py` Decomposition Checklist

**Source:** `backend/app.py` (1,577 lines, audited at start of refactor)
**Strategy:** Per-domain Flask Blueprint + service layer, registered through `backend/app_factory.py`.
**Safety net:** 435 tests (incl. `tests/golden/test_routes_baseline.py`) — must remain GREEN after every phase.

---

## Module-level helpers (move to `backend/utils/`)

| Symbol                              | Lines       | Destination                                | Phase |
| ----------------------------------- | ----------- | ------------------------------------------ | :---: |
| `_interface_status_trace`           | 36–78       | `backend/utils/interface_status.py`        |   2   |
| `_cisco_interface_detailed_trace`   | 80–122      | `backend/utils/interface_status.py`        |   2   |
| `_iface_status_lookup`              | 154–164     | `backend/utils/interface_status.py`        |   2   |
| `_merge_cisco_detailed_flap`        | 166–198     | `backend/utils/interface_status.py`        |   2   |
| `_transceiver_errors_display`       | 124–138     | `backend/utils/transceiver_display.py`     |   2   |
| `_transceiver_last_flap_display`    | 140–152     | `backend/utils/transceiver_display.py`     |   2   |
| `_single_ping` + `_MAX_PING_DEVICES`| 561–582     | `backend/utils/ping.py`                    |   2   |
| `_wan_rtr_has_bgp_as`               | 1139–1159   | `backend/utils/bgp_helpers.py`             |   2   |
| `_bgp_resource`                     | 1064–1072   | stays as Flask-aware `_bgp_resource()` thin wrapper around `bgp_lg`; live in `bgp_bp.py` (Phase 7) |   7   |
| `_inventory_path`                   | 295–308     | already in `app_factory.py`; consolidate to `backend/utils/paths.py` (later cleanup) |  12   |
| `_device_row`                       | 429–438     | becomes `InventoryService._normalise_row` (Phase 3) |   3   |
| Reports persistence helpers (`_reports_dir`, `_reports_index_path`, `_report_path`, `_load_reports_index`, `_save_reports_index`, `_persist_report`, `_load_report`, `_delete_report`) | 215–293 | already mirrored in `backend/repositories/report_repository.py` — delete from `app.py` in Phase 11 |  11   |
| `_run_devices`                      | 625–632     | `RunsService` (Phase 11)                   |  11   |

---

## Routes (30 endpoints) → Blueprints

### Already extracted (do not touch)
- `health_bp` — `/api/health`, `/`
- `inventory_bp` (read) — `/api/fabrics`, `/api/sites`, `/api/halls`, `/api/roles`, `/api/devices`, `/api/devices-arista`, `/api/devices-by-tag`, `/api/inventory`
- `notepad_bp` — notepad CRUD

### Phase 3 → extend `inventory_bp` (write side)
| Method | Path                       | `app.py` line | Notes                                    |
| ------ | -------------------------- | :-----------: | ---------------------------------------- |
| POST   | `/api/inventory/device`    | 440           | Add device                               |
| PUT    | `/api/inventory/device`    | 459           | Update device                            |
| DELETE | `/api/inventory/device`    | 484           | Delete device                            |
| POST   | `/api/inventory/import`    | 502           | Bulk import (CSV)                        |

### Phase 4 → new `commands_bp`
| Method | Path                          | `app.py` line |
| ------ | ----------------------------- | :-----------: |
| GET    | `/api/commands`               | 535           |
| GET    | `/api/parsers/fields`         | 545           |
| GET    | `/api/parsers/<command_id>`   | 552           |

### Phase 5 → new `network_ops_bp` (+ SPA fallback)
| Method | Path        | `app.py` line | Notes                                |
| ------ | ----------- | :-----------: | ------------------------------------ |
| POST   | `/api/ping` | 584           | Use `InputSanitizer`, `_single_ping` |
| GET    | `/`         | 1569          | SPA fallback (or keep in `health_bp`) |

### Phase 6 → new `credentials_bp`
| Method | Path                                | `app.py` line |
| ------ | ----------------------------------- | :-----------: |
| GET    | `/api/credentials`                  | 1480          |
| POST   | `/api/credentials`                  | 1486          |
| DELETE | `/api/credentials/<name>`           | 1513          |
| POST   | `/api/credentials/<name>/validate`  | 1520          |

### Phase 7 → new `bgp_bp`
| Method | Path                              | `app.py` line |
| ------ | --------------------------------- | :-----------: |
| GET    | `/api/bgp/status`                 | 1074          |
| GET    | `/api/bgp/history`                | 1083          |
| GET    | `/api/bgp/visibility`             | 1092          |
| GET    | `/api/bgp/looking-glass`          | 1101          |
| GET    | `/api/bgp/bgplay`                 | 1110          |
| GET    | `/api/bgp/as-info`                | 1121          |
| GET    | `/api/bgp/announced-prefixes`     | 1130          |
| GET    | `/api/bgp/wan-rtr-match`          | 1161          |

### Phase 8 → new `network_lookup_bp`
| Method | Path                            | `app.py` line |
| ------ | ------------------------------- | :-----------: |
| POST   | `/api/find-leaf`                | 950           |
| POST   | `/api/find-leaf-check-device`   | 983           |
| POST   | `/api/nat-lookup`               | 1019          |

### Phase 9 → new `transceiver_bp` + `TransceiverService`
| Method | Path                                | `app.py` line |
| ------ | ----------------------------------- | :-----------: |
| POST   | `/api/transceiver`                  | 648           |
| POST   | `/api/transceiver/recover`          | 768           |
| POST   | `/api/transceiver/clear-counters`   | 843           |

### Phase 10 → new `device_commands_bp`
| Method | Path                       | `app.py` line |
| ------ | -------------------------- | :-----------: |
| POST   | `/api/arista/run-cmds`     | 310           |
| GET    | `/api/router-devices`      | 361           |
| POST   | `/api/route-map/run`       | 376           |
| POST   | `/api/custom-command`      | 918           |

### Phase 11 → new `runs_bp` + `reports_bp`
| Method | Path                          | `app.py` line | Blueprint    |
| ------ | ----------------------------- | :-----------: | ------------ |
| POST   | `/api/run/device`             | 634           | `runs_bp`    |
| POST   | `/api/run/pre/create`         | 1210          | `runs_bp`    |
| POST   | `/api/run/pre/restore`        | 1240          | `runs_bp`    |
| POST   | `/api/run/pre`                | 1267          | `runs_bp`    |
| POST   | `/api/run/post`               | 1289          | `runs_bp`    |
| POST   | `/api/run/post/complete`      | 1333          | `runs_bp`    |
| POST   | `/api/diff`                   | 1395          | `runs_bp`    |
| GET    | `/api/run/result/<run_id>`    | 1415          | `runs_bp`    |
| GET    | `/api/reports`                | 1423          | `reports_bp` |
| GET    | `/api/reports/<run_id>`       | 1433          | `reports_bp` |
| DELETE | `/api/reports/<run_id>`       | 1458          | `reports_bp` |

---

## Phase 12 — Final `app.py` shape (79 lines, target met)

`backend/app.py` now contains **only**:

1. Path-bootstrap (so `flask run` works from the repo root).
2. Legacy `_*` helper re-exports from `backend/utils/*` (kept so any
   in-tree caller resolving `backend.app._foo` keeps working).
3. The `app = Flask(...)` global + `SECRET_KEY` config (preserved
   because `backend.app_factory.create_app` imports the module to get
   the global instance).
4. `creds.init_db(...)` for legacy boot-time credential init.
5. The `if __name__ == "__main__"` shim.

Every route lives in a per-domain blueprint registered by
`backend/app_factory.py::_register_blueprints`:

| Blueprint                    | Routes                                                 |
| ---------------------------- | ------------------------------------------------------ |
| `health_bp`                  | `/api/health`, `/api/v2/health`                        |
| `inventory_bp`               | 8 read + 4 write inventory endpoints                   |
| `notepad_bp`                 | notepad CRUD                                           |
| `commands_bp`                | `/api/commands`, `/api/parsers/*`                      |
| `network_ops_bp`             | `/api/ping`, `/` (SPA fallback)                        |
| `credentials_bp`             | 4 credential endpoints                                 |
| `bgp_bp`                     | 8 BGP looking-glass endpoints                          |
| `network_lookup_bp`          | `/api/find-leaf`, `/api/find-leaf-check-device`, `/api/nat-lookup` |
| `transceiver_bp`             | `/api/transceiver`, `/api/transceiver/recover`, `/api/transceiver/clear-counters` |
| `device_commands_bp`         | `/api/arista/run-cmds`, `/api/router-devices`, `/api/route-map/run`, `/api/custom-command` |
| `runs_bp`                    | 8 pre/post run endpoints                               |
| `reports_bp`                 | 3 saved-report endpoints                               |

**Total**: 12 blueprints, 50+ routes, all wired through the factory.

---

## Per-phase verification protocol (TDD)

For each phase:
1. **RED** — write failing test that proves new module/route lives in the new home (or replicates the legacy contract from a new file). Run it, confirm RED, commit `test: <phase> add <X>`.
2. **GREEN** — minimal implementation to pass new test + keep all 435 baseline tests GREEN. Commit `refactor(phase-N): extract <X>`.
3. **REFACTOR** — polish (docstrings, type hints, ruff clean), re-run full suite, commit `refactor(phase-N): cleanup`.
4. **VERIFY** — `python -m pytest -q` (must show ≥ 435 passing), then proceed.

Each phase's commits MUST live on `refactor/ood-tdd` branch and be reachable from current `HEAD`.
