import dataclasses
import pathlib
import typing

import dotenv

ServiceName = typing.Literal["jira", "bitbucket"]


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class ServiceConfig:
    url: str
    token: str
    project: str


def load_config(service_name: ServiceName) -> ServiceConfig:
    environment_path = pathlib.Path.cwd() / ".env"
    if not environment_path.is_file():
        raise ValueError(".env file not found")

    environment = dotenv.dotenv_values(environment_path)
    prefix = service_name.upper()
    required_keys = (f"{prefix}_URL", f"{prefix}_TOKEN", f"{prefix}_PROJECT")
    missing_keys = [key for key in required_keys if not (environment.get(key) or "").strip()]
    if missing_keys:
        raise ValueError(f"Missing environment variables: {', '.join(missing_keys)}")

    return ServiceConfig(
        url=typing.cast("str", environment[required_keys[0]]).strip(),
        token=typing.cast("str", environment[required_keys[1]]).strip(),
        project=typing.cast("str", environment[required_keys[2]]).strip(),
    )
