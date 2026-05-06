import importlib
import sys

from .core import AutoMesh


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m mc_automesh", description="mc-automesh CLI")
    parser.add_argument(
        "command",
        choices=["publish-path", "publish-module", "serve", "run"],
        help="Command",
    )
    parser.add_argument("--service-name", required=True)
    parser.add_argument("--registry-url", default="")
    parser.add_argument("--runtime", default="python")
    parser.add_argument("--mcp-transport", default="stdio")
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--heartbeat-interval-s", type=int, default=None)
    parser.add_argument("--mesh-id", default=None)
    parser.add_argument("--path", default=None)
    parser.add_argument("--module", default=None)

    args = parser.parse_args()

    mesh = AutoMesh(
        service_name=args.service_name,
        registry_url=args.registry_url,
        runtime=args.runtime,
        mcp_transport=args.mcp_transport,
        endpoint=args.endpoint,
        heartbeat_interval_s=args.heartbeat_interval_s,
        mesh_id=args.mesh_id,
    )

    if args.command in ("publish-path", "run"):
        if not args.path:
            sys.stderr.write("--path richiesto\n")
            sys.exit(2)
        mesh.publish_path(args.path)

    if args.command == "publish-module":
        if not args.module:
            sys.stderr.write("--module richiesto\n")
            sys.exit(2)
        mod = importlib.import_module(args.module)
        mesh.publish_module(mod)

    if args.command in ("serve", "run"):
        mesh.serve()


if __name__ == "__main__":
    main()
