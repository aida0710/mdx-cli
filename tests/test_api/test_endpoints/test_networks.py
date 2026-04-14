import httpx
import respx

from mdx_cli.api.endpoints.networks import (
    create_acl,
    create_dnat,
    delete_acl,
    delete_dnat,
    get_segment_summary,
    list_acls,
    list_assignable_ips,
    list_dnats,
    list_segments,
    update_acl,
    update_dnat,
)
from mdx_cli.models.network import (
    ACLCreateRequest,
    ACLUpdateRequest,
    DNATRequest,
)


@respx.mock
def test_list_segments():
    respx.get("/api/segment/project/proj-1/all/").mock(
        return_value=httpx.Response(
            200, json=[{"uuid": "seg-1", "name": "Segment 1"}]
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    segments = list_segments(client, "proj-1")
    assert len(segments) == 1
    assert segments[0].uuid == "seg-1"


@respx.mock
def test_get_segment_summary():
    respx.get("/api/segment/seg-1/summary/").mock(
        return_value=httpx.Response(
            200, json={"vlan_id": 583, "vni": 583, "ip_range": "10.0.1.0/21"}
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    summary = get_segment_summary(client, "seg-1")
    assert summary.vlan_id == 583
    assert summary.ip_range == "10.0.1.0/21"


@respx.mock
def test_list_acls():
    respx.get("/api/acl/segment/seg-1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "uuid": "acl-1",
                        "protocol": "TCP",
                        "src_address": "0.0.0.0",
                        "src_mask": "24",
                        "src_port": "Any",
                        "dst_address": "10.0.1.0",
                        "dst_mask": "21",
                        "dst_port": "Any",
                    }
                ]
            },
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    acls = list_acls(client, "seg-1")
    assert len(acls) == 1
    assert acls[0].protocol == "TCP"


@respx.mock
def test_list_dnats():
    respx.get("/api/dnat/project/proj-1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "uuid": "dnat-1",
                        "pool_address": "203.0.113.10",
                        "segment": "テストセグメント",
                        "dst_address": "10.0.0.20",
                    }
                ]
            },
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    dnats = list_dnats(client, "proj-1")
    assert len(dnats) == 1
    assert dnats[0].pool_address == "203.0.113.10"


# --- ACL CRUD ---


@respx.mock
def test_create_acl():
    respx.post("/api/acl/").mock(
        return_value=httpx.Response(
            201,
            json={
                "uuid": "acl-new",
                "protocol": "TCP",
                "src_address": "0.0.0.0",
                "src_mask": "0",
                "src_port": "Any",
                "dst_address": "10.0.0.1",
                "dst_mask": "32",
                "dst_port": "22",
            },
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    req = ACLCreateRequest(
        protocol="TCP",
        src_address="0.0.0.0",
        src_mask="0",
        src_port="Any",
        dst_address="10.0.0.1",
        dst_mask="32",
        dst_port="22",
        segment="seg-1",
    )
    acl = create_acl(client, req)
    assert acl.uuid == "acl-new"
    assert acl.protocol == "TCP"


@respx.mock
def test_update_acl():
    respx.put("/api/acl/acl-1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "uuid": "acl-1",
                "protocol": "UDP",
                "src_address": "0.0.0.0",
                "src_mask": "0",
                "src_port": "Any",
                "dst_address": "10.0.0.1",
                "dst_mask": "32",
                "dst_port": "80",
            },
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    req = ACLUpdateRequest(
        protocol="UDP",
        src_address="0.0.0.0",
        src_mask="0",
        src_port="Any",
        dst_address="10.0.0.1",
        dst_mask="32",
        dst_port="80",
    )
    acl = update_acl(client, "acl-1", req)
    assert acl.uuid == "acl-1"
    assert acl.protocol == "UDP"


@respx.mock
def test_delete_acl():
    respx.delete("/api/acl/acl-1/").mock(
        return_value=httpx.Response(204)
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    delete_acl(client, "acl-1")


# --- DNAT CRUD ---


@respx.mock
def test_create_dnat():
    respx.post("/api/dnat/").mock(
        return_value=httpx.Response(201)
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    req = DNATRequest(
        pool_address="203.0.113.12",
        segment="seg-1",
        dst_address="10.0.0.1",
    )
    create_dnat(client, req)


@respx.mock
def test_update_dnat():
    respx.put("/api/dnat/dnat-1/").mock(
        return_value=httpx.Response(200)
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    req = DNATRequest(
        pool_address="203.0.113.12",
        segment="seg-1",
        dst_address="10.0.0.1",
    )
    update_dnat(client, "dnat-1", req)


@respx.mock
def test_delete_dnat():
    respx.delete("/api/dnat/dnat-1/").mock(
        return_value=httpx.Response(204)
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    delete_dnat(client, "dnat-1")


# --- 補助API ---


@respx.mock
def test_list_assignable_ips():
    respx.get("/api/global_ip/project/proj-1/assignable/").mock(
        return_value=httpx.Response(
            200, json=["203.0.113.10", "203.0.113.11"]
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    ips = list_assignable_ips(client, "proj-1")
    assert ips == ["203.0.113.10", "203.0.113.11"]
