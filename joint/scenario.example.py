"""Illustrate passing an identifier between APIs, not a complete joint lab scenario.

Replace the paths, fields and expected state with the contract of your card.
The actual state transfer between services belongs to the student's project.

Copy it as joint/my-scenario.py, adapt it, then run from the root of the joint project:

    uv run --no-project --python 3.14 python web/tools/workload/run.py joint/my-scenario.py \\
        --base web=http://localhost:8080 --base dpc=http://localhost:8000 \\
        --env web_token=WEB_TOKEN --env dpc_token=DPC_TOKEN --set resource_id=resource-1 \\
        --runs 1 --pause 1 --out runs/joint-demo-01
"""

from urllib.parse import quote
from uuid import uuid4


def validate(bases, settings):
    if not {"web", "dpc"}.issubset(bases):
        raise ValueError("supply both web and dpc bases")
    if not all(settings.get(name) for name in ("web_token", "dpc_token", "resource_id")):
        raise ValueError("supply resource_id, web_token and dpc_token")


def scenario(ctx):
    web_headers = {"Authorization": f"Bearer {ctx.settings['web_token']}"}

    created = ctx.request(
        "POST",
        "/v1/items",
        service="web",
        body={"resource_id": ctx.settings["resource_id"]},
        headers={**web_headers, "Idempotency-Key": str(uuid4())},
        expected=(201,),
        label="web-create",
    )
    identifier = str(created.json()["id"])

    ctx.request(
        "POST",
        "/v1/requests",
        service="dpc",
        body={"source_id": identifier},
        expected=(202,),
        label="dpc-submit",
        headers={
            "Authorization": f"Bearer {ctx.settings['dpc_token']}",
            "Idempotency-Key": str(uuid4()),
        },
    )

    ctx.poll(
        f"/v1/items/{quote(identifier, safe='')}",
        service="web",
        done=lambda response: response.json()["status"] == "processed",
        headers=web_headers,
        label="web-result",
    )
