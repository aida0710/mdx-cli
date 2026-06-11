from mdx_cli.models.pack import PACK_SPECS


def test_pack_specs_cpu():
    spec = PACK_SPECS["cpu"]
    assert spec.max_num == 152
    assert spec.mem_per_pack_gb == 1.51
    assert spec.cores_per_pack == 1
    assert spec.default_num == 3


def test_pack_specs_gpu():
    spec = PACK_SPECS["gpu"]
    assert spec.max_num == 8
    assert spec.mem_per_pack_gb == 57.60
    assert spec.cores_per_pack == 18
    assert spec.default_num == 1


def test_resource_summary_cpu():
    """CPUパックは コア数 / RAM を表示する"""
    assert PACK_SPECS["cpu"].resource_summary(8) == "8コア / 12.1GB RAM"


def test_resource_summary_gpu():
    """GPUパックは コア数 / GPU数 / RAM を表示する"""
    assert PACK_SPECS["gpu"].resource_summary(2) == "36コア / 2GPU / 115.2GB RAM"
