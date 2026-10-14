from app.modules.orders.preconditions import EffectivePrecondition, precondition_key


def pre(category, value=None, unit=None, text="x"):
    return EffectivePrecondition(
        category=category,
        name="n",
        duration_value=value,
        duration_unit=unit,
        patient_instructions=text,
    )


def test_la_llave_es_estable_y_unica_por_precondicion_unificada():
    assert precondition_key(pre("ayuno", 8, "horas")) == precondition_key(
        pre("ayuno", 12, "horas")
    )  # misma categoria con duracion = un solo item
    assert precondition_key(pre("ayuno", 8, "horas")) != precondition_key(
        pre("tabaco", 8, "horas")
    )


def test_sin_duracion_la_llave_depende_del_texto():
    a = precondition_key(pre("recoleccion_muestra", text="Primera orina"))
    b = precondition_key(pre("recoleccion_muestra", text="primera  orina "))
    c = precondition_key(pre("recoleccion_muestra", text="Aseo previo"))
    assert a == b and a != c


def test_la_llave_es_texto_corto():
    assert isinstance(precondition_key(pre("ayuno", 8, "horas")), str)
    assert len(precondition_key(pre("recoleccion_muestra", text="x" * 500))) <= 64
