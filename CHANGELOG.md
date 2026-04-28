# Changelog

All notable changes to hip-cargo are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-04-17

### Added

- Add StimelaMeta dataclass to keep track of stimela metadata (favour over old dict approach)

### Documentation

- Address copilot review on PR #74
- Add instructions for building image locally with apptainer
- Update README with more comprehensive contribution guidelines. Sync templates.

### Fixed

- **release**: Use conventional commit format for tbump version bumps
- Git add missing files


## [0.2.0rc2] - 2026-04-10

### Miscellaneous

- Update container image name

### Other

- Bump version to 0.2.0rc2
- Use pep440 type container tags instead of symver


## [0.2.0rc1] - 2026-04-09

### Added

- **init**: Update scaffolding templates for _container_image.py
- Replace entry-point lookup with _container_image module import
- **init**: Add git-cliff template and tbump integration for scaffolded projects
- Add git-cliff configuration for automated changelog generation
- **init**: Add git-cliff template and tbump integration for scaffolded projects
- Add git-cliff configuration for automated changelog generation

### CI

- Retarget update-cabs workflow to _container_image.py
- Retarget tbump container tag hooks to _container_image.py
- Integrate git-cliff into tbump release workflow
- Integrate git-cliff into tbump release workflow

### Documentation

- Update CLAUDE.md for _container_image.py, remove entry-point doc
- Add conventional commit guidance to CLAUDE.md for AI agents
- Add conventional commit guidelines and update contributing workflow
- Add conventional commit guidance to CLAUDE.md for AI agents
- Add conventional commit guidelines and update contributing workflow

### Fixed

- Fix failing test
- Address code review findings
- Remove spec-violating entry point and importlib_metadata dependency
- Improve cliff.toml template spacing and add deps(chore) parser
- Improve cliff.toml template spacing and add deps(chore) parser

### Miscellaneous

- Exlcude changelog from linting checks during pre-commit

### Other

- Bump version to 0.2.0rc1
- Update container name
- Modify tbump config to allow pre-releases and patches
- Use uvx to run git-cliff in tbump
- Address copilot comments
- Merge in gitcliff changes
- Streamline copilot instructions for reviews
- Simplify monolithic CLAUDE.md file and include rules
- Merge main
- Add git-cliff integration

### Testing

- Update container tag regex tests for _container_image.py syntax


## [0.1.8] - 2026-04-08

### Added

- Update templates for Container URL image discovery
- Generate get_container_image() call in container fallback

### Changed

- Use get_container_image() in generate_cabs
- Replace CWD-walk image discovery with importlib.metadata

### Dependencies

- Update uv-build requirement

### Fixed

- Manually revert to correct version [skip checks]
- Fix merge conflicts
- Fix PackageNotFoundError comment
- Clean up dead imports and docstring in runner.py

### Miscellaneous

- Final cleanup — fix stale docstring and shorten error message
- Update hip-cargo tbump.toml for Container URL workflow
- Regenerate hip-cargo CLI files with new fallback pattern

### Other

- Bump version to 0.1.8
- Address copilot comments
- Move image name to entry-points section in pyproject.toml
- Bump version to 0.1.8
- Attempt to [skip checks] again
- Attempt to [skip checks]
- Attempt to report job status even when CI is skipped
- Remove unnecessary tbump [[file]] check [skip ci]
- Update container name in pyproject.toml
- Address copilot comment
- Add tests for regex etc
- Simplify readme and update agentic instructions
- Sync to reflect new branch in metadata
- Add multi-line command for update-cabs workflow
- Add ruff as main dependency
- Copilot comments
- Sync with main
- Uv sync to update cabs
- Hardcode image in update-cabs workflow

### Testing

- Test pre-commit overwrite in pyproject.toml
- Test pre-commit overwrite in pyproject.toml
- Testing pre-commits


## [0.1.7] - 2026-03-28

### CI

- Bump actions/create-github-app-token in the github-actions group
- Bump actions/create-github-app-token in the github-actions group

### Documentation

- Document single vs multi CLI mode Typer behaviour

### Fixed

- Skip CI on cab update commits, address PR review feedback
- Fix formatting
- Fix Optional[...] for ... | None type parameters
- Skip CI on cab update commits, address PR review feedback
- Fix formatting
- Fix Optional[...] for ... | None type parameters
- Fix end message for init pp when cli-mode==single

### Other

- Bump version to 0.1.7


## [0.1.6] - 2026-03-13

### Fixed

- Fix tbump config -> only delete sentinel once cabs have been generated
- Fix uv.lock

### Miscellaneous

- Update cab image tags to latest [skip ci]

### Other

- Bump version to 0.1.6
- Revert tbump version bump manually
- Add quotes around wildcard in hip-cargo generate-cabs command in tbump
- Address copilot comments
- Remove scripts/generate_cabs.py and move functionality into core app
- Address copilot comments
- Also update image name in decorators when running generate-cabs script during pre-commit


## [0.1.5] - 2026-03-10

### CI

- Bump the github-actions group with 3 updates
- Bump actions/setup-python from 5 to 6 in the github-actions group

### Fixed

- Fix how defaults for special types are added to CLI
- Fix colons in help strings + add image name during pfb tests
- Fix merge conflicts from 0.1.4

### Miscellaneous

- Update cab image tags to latest [skip ci]

### Other

- Bump version to 0.1.5
- Rather let uv manage the lock file, just use a before_commit hook in tbump
- Add uv.lock to the list of versions tbump bumps
- Add a cron job every Monday and Thursday @ 2h30am UTC
- Prevent pull_request action triggering exclusively on the main branch
- Revert "Update github actions on clause"

This reverts commit 25e9d432ef5b5a2678a8057eeca2647103d746f0.
- Update github actions on clause
- Address copilot comments
- Add backend fallback logic and keep track of rich_help_panel in stimela parameter metadata


## [0.1.4] - 2026-02-27

### CI

- Bump actions/create-github-app-token in the github-actions group

### Miscellaneous

- Update cab image tags to latest [skip ci]
- Update cab image tags to latest [skip ci]

### Other

- Bump version to 0.1.4
- Add ListStr dtypes and parsers etc. to avoid the clumsy comma separted string unpacking and document them. Update README.md with new Quick start and Quirks sections
- Use actions/setup-python to install python before running uv
- Remove uv.lock from gitignore template
- Separate git commit and git checkout commands in init command to allow for older git versions
- Expand ~ when project-name is passed in as str. Don't use _ in default cli_command
- Add container runner logic and backend options to generated functions to select backend. docker, podman, apptainer and singularity supported
- Pin uv version in actions
- Set up credentials in the init commit
- Add init command to initialise blank project structure


## [0.1.3] - 2026-02-10

### CI

- Bump the github-actions group across 1 directory with 2 updates

### Changed

- Complete LibCST migration and code quality improvements

### Dependencies

- Update uv-build requirement

### Fixed

- Fix circular tbump logic and remove unnecessary pre-commit hooks
- Fix automated ruff formatting of code
- Fix issues with _ vs -

### Miscellaneous

- Update cab image tags to latest [skip ci]
- Update cab image tags to latest [skip ci]

### Other

- Bump version to 0.1.3
- Update .github/workflows/update-cabs.yml

Co-authored-by: Copilot <175728472+Copilot@users.noreply.github.com>
- Use privileged app to run update-cabs workflow
- Remove files filter from cab gen pre-commit
- Use tbump to also bump cab versions before pushing to PYPI
- Don't write empty info fields or put stimela dtype in help string
- Add '' around implicit content in cabs
- Install hip-cargo before regenerating cabs
- Add workflow to update ghcr image name on merge to main
- Address copilot comments
- Add copilot-instrictions.md
- Add stimela options dict to Annotated type hints
- Add stimela config dict to Annotated type hints
- Update actions cache to v5
- Don't use uv run when using ruff programmatically
- Check for Stimela dtype: in generate-function
- Add more stimela outputs
- Remove debug statements
- Check for must_exist
- Add additional stimela outputs in generate-function
- Simplify pfb rountrip test
- Add additional stimela params for output decorator
- Remove debug print statement
- Do not generate cabs in CI, simple push the container
- Workflow should not fail if cabs change in new branch
- Workflow should not fail if cabs change in new branch
- Format yaml info strings one sentence per line
- Respond to copilot review
- Add roundtrip test for pfb cabs
- Update stimela cabs to reference ghcr.io/landmanbester/hip-cargo:latest
- Update stimela cabs to version dependabot/github_actions/github-actions-80d2e6fa0b
- Update stimela cabs to reference ghcr.io/landmanbester/hip-cargo:latest
- Update stimela cabs to version stimelatests
- Address copilot comments
- Update stimela cabs to version stimelatests
- Generate branch name tag on push to PR
- Save package name in workflow output
- Remove double wildcard pattern
- Modify Dockerfile to not automatically invoke cargo
- Add update-cabs-and-publish workflow in favour of publish-container
- Add update-cabs-and-publish workflow in favour of publish-container
- Remove --pyprojecttoml in favour of --image
- Add update_readme 5
- Add update_readme 5
- Add update_readme 4
- Add update_readme 3
- Add update_readme 3
- Add update_readme 2
- Add code snippets 1
- Update GHCR link
- Readme edits
- Skip tests that require generate-function
- Push image on merge to main
- Sync without dev dependencies
- Try auto document README
- Reorder to place outputs last
- Generate-cab -> generate-cabs and allow wildcard inputs. Use ast to avoid installing package
- Make output_path positional
- Start adding tests that actually test if stimela can pull and run the containers specified as image: ghcr.io/githubid/package:version

### Testing

- Test pre-commit generate-cabs branch name again
- Test branch renaming in pre-commit hooks
- Tests to readme


## [0.1.2] - 2025-11-17

### Other

- Bump version to 0.1.2
- Also downgrade version in __init__.py, test on python3.13
- Roll back version
- Use pypi enviroment in publish workflow
- Bump version to 0.1.2
- Update lock file


## [0.1.1] - 2025-11-16

### Fixed

- Fix sha/tag setting in publish =-container

### Other

- Bump version to 0.1.1
- Dfr


## [0.1.0] - 2025-11-14

### CI

- Bump docker/build-push-action in the github-actions group
- Bump astral-sh/setup-uv from 6 to 7 in the github-actions group

### Fixed

- Fix project url config
- Fix formatting errors
- Fix formatting
- Fix cab generation script

### Other

- Bump version to 0.1.0
- Add metadata
- Use Path | None
- Add round trip conversion test
- Update ruff version in pre-commit hooks
- Add pre-commit hooks
- Restructure into hip-cargo format
- Update README.md

Co-authored-by: Copilot <175728472+Copilot@users.noreply.github.com>
- Update .github/workflows/publish-container.yml

Co-authored-by: Copilot <175728472+Copilot@users.noreply.github.com>
- Update Dockerfile

Co-authored-by: Copilot <175728472+Copilot@users.noreply.github.com>
- Add dockerfile and publish-container workflow
- Add instructions for associating a container on ghcr.io with package
- Add .devcontainer for codespaces
- Updates generate-function command
- Handle Optional
- Rewrite tests for new functionality


## [0.0.2] - 2025-10-13

### CI

- Bump astral-sh/setup-uv from 6 to 7 in the github-actions group
- Bump the github-actions group with 2 updates

### Dependencies

- Update uv-build requirement from <0.9.0,>=0.8.3 to >=0.8.3,<0.10.0

### Fixed

- Fix tbump config
- Fix formatting
- Fix formatting again
- Fix Option(None, ...) bug

### Other

- Bump version to 0.0.2
- Update lock file
- Reset version
- Add publish workflow
- Formatting
- Check in callbacks
- Add callbacks module
- Update readme
- Remove ipdb
- Convert apps to use Annotated style
- Remove failing security scan step from CI
- Format with ruff
- Simplify test suite
- Update CLAUDE.md file
- Update readme and fix function generator
- Fix cab_to_function
- Set up testing and CI
- Add functionality for annotated type hints
- Initial implementation of hip-cargo cab generator
- Initial commit


[0.2.0]: https://github.com/landmanbester/hip-cargo/compare/v0.2.0rc2...v0.2.0
[0.2.0rc2]: https://github.com/landmanbester/hip-cargo/compare/v0.2.0rc1...v0.2.0rc2
[0.2.0rc1]: https://github.com/landmanbester/hip-cargo/compare/v0.1.8...v0.2.0rc1
[0.1.8]: https://github.com/landmanbester/hip-cargo/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/landmanbester/hip-cargo/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/landmanbester/hip-cargo/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/landmanbester/hip-cargo/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/landmanbester/hip-cargo/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/landmanbester/hip-cargo/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/landmanbester/hip-cargo/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/landmanbester/hip-cargo/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/landmanbester/hip-cargo/compare/v0.0.2...v0.1.0
[0.0.2]: https://github.com/landmanbester/hip-cargo/releases/tag/v0.0.2

