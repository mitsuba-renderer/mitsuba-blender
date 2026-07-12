# Test suite

The tests run with pytest **inside headless Blender**, since they exercise
`bpy` and the addon itself. `tests/run.py` is a plain host-side Python script
that launches Blender, runs pytest in it, and propagates the result.

## Requirements

- Set the `BLENDER` environment variable to a Blender 4.2+ executable:

  ```sh
  export BLENDER=/path/to/blender-4.2.22-linux-x64/blender
  ```

- Blender's bundled Python must have `mitsuba` and `pytest` installed:

  ```sh
  /path/to/blender-4.2.22-linux-x64/4.2/python/bin/python3.11 -m pip install mitsuba==3.9.0 pytest
  ```

## Running

```sh
python3 tests/run.py                     # all fast tests (unit/roundtrip/golden)
python3 tests/run.py tests/unit/test_smoke.py       # one file
python3 tests/run.py tests/unit/test_smoke.py -k engine -v   # any pytest args
python3 tests/run.py --all               # include slow and packaging tests
python3 tests/run.py -m packaging        # only packaging tests
```

Golden render tests compare against small EXR references committed under
`tests/golden/refs`. After an intentional change in rendering output,
regenerate them with:

```sh
python3 tests/run.py tests/golden --update-refs
```

All arguments except `--all` are forwarded to pytest verbatim. The launcher
prints the tail of the pytest report plus a final `PASS`/`FAIL` line; the full
(noisy) Blender output is written to a log file whose path is printed at the
end. The exit code is pytest's exit code (non-zero on failure, also when
Blender crashes before pytest can report).

## Markers

- `@pytest.mark.slow`: takes more than a few seconds (e.g. golden renders at
  higher spp). Skipped by default, included with `--all` or an explicit `-m`.
- `@pytest.mark.packaging`: builds the extension zip and installs it into a
  factory Blender. Slow; same opt-in rules.

CI runs the full set (`--all`).

## Layout

- `run.py`: host-side launcher (see above).
- `_bootstrap.py`: runs inside Blender; invokes `pytest.main()` and reports
  the exit code back to `run.py`.
- `conftest.py`: shared fixtures:
  - `mi_addon` (session): symlinks the in-repo extension into Blender's
    `user_default` extension repository and enables it.
  - `fresh_scene`: resets Blender to the factory startup scene.
  - `render_dict`: renders a Mitsuba scene dict, returns a numpy array.
  - `compare_images`: mean/RMSE image comparison with tolerances.
- `unit/`, `roundtrip/`, `golden/`: test directories discovered by default.

The remaining `test_*.py` files directly under `tests/` are legacy tests that
require the old `scripts/run_tests.py` runner; the new harness ignores them.
