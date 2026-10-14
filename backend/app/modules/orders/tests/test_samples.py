from app.modules.orders.samples import group_samples


def make_type(id_, name="Tubo", color="#FF0000", draw_order=1, code=None):
    return {
        "id": id_,
        "code": code or id_.upper(),
        "name": name,
        "cap_color_hex": color,
        "draw_order": draw_order,
        "collection_instructions": None,
    }


def make_exam(code, *links):
    return {
        "code": code,
        "sample_types": [
            {
                "sample_type_id": sid,
                "is_preferred": pref,
                "required_volume_ml": vol,
                "is_active": True,
            }
            for sid, pref, vol in links
        ],
    }


TYPES = {
    "red": make_type("red", "Tapa roja", "#DC2626", draw_order=2),
    "lila": make_type("lila", "Tapa lila", "#7C3AED", draw_order=1),
}


def test_examenes_con_el_mismo_tipo_comparten_un_tubo():
    tests = [
        make_exam("COL", ("red", True, 3.0)),
        make_exam("TRI", ("red", True, 5.0)),
    ]
    tubes = group_samples(tests, TYPES)
    assert len(tubes) == 1
    assert tubes[0].sample_type_id == "red"
    assert tubes[0].required_volume_ml == 5.0
    assert tubes[0].test_codes == ["COL", "TRI"]


def test_tubos_ordenados_por_orden_de_extraccion():
    tests = [make_exam("A", ("red", True, 3.0)), make_exam("B", ("lila", True, 2.0))]
    assert [t.sample_type_id for t in group_samples(tests, TYPES)] == ["lila", "red"]


def test_usa_el_tipo_preferido_activo():
    tests = [
        {
            "code": "X",
            "sample_types": [
                {
                    "sample_type_id": "lila",
                    "is_preferred": False,
                    "required_volume_ml": 1,
                    "is_active": True,
                },
                {
                    "sample_type_id": "red",
                    "is_preferred": True,
                    "required_volume_ml": 4,
                    "is_active": True,
                },
            ],
        }
    ]
    assert group_samples(tests, TYPES)[0].sample_type_id == "red"


def test_ignora_tipos_inactivos_y_cae_al_primero_activo():
    tests = [
        {
            "code": "X",
            "sample_types": [
                {
                    "sample_type_id": "red",
                    "is_preferred": True,
                    "required_volume_ml": 4,
                    "is_active": False,
                },
                {
                    "sample_type_id": "lila",
                    "is_preferred": False,
                    "required_volume_ml": 2,
                    "is_active": True,
                },
            ],
        }
    ]
    assert group_samples(tests, TYPES)[0].sample_type_id == "lila"


def test_examen_sin_tipo_activo_se_omite():
    assert group_samples([make_exam("X")], TYPES) == []


def test_tipo_desconocido_usa_valores_por_defecto():
    tubes = group_samples([make_exam("X", ("zzz", True, None))], TYPES)
    assert tubes[0].name == "zzz"
    assert tubes[0].required_volume_ml is None
