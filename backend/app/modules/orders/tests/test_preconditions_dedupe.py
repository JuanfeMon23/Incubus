from app.modules.orders.preconditions import EffectivePrecondition, dedupe_preconditions


def p(category, value=None, unit=None, text="x", name="n"):
    return EffectivePrecondition(
        category=category,
        name=name,
        duration_value=value,
        duration_unit=unit,
        patient_instructions=text,
    )


def test_ayuno_8h_y_16h_deja_solo_16h():
    out = dedupe_preconditions([p("ayuno", 8, "horas"), p("ayuno", 16, "horas")])
    assert len(out) == 1 and out[0].duration_value == 16


def test_misma_duracion_se_muestra_una_vez():
    out = dedupe_preconditions([p("ayuno", 12, "horas"), p("ayuno", 12, "horas")])
    assert len(out) == 1


def test_unidades_se_normalizan_a_minutos():
    out = dedupe_preconditions([p("ayuno", 1, "dias"), p("ayuno", 20, "horas")])
    assert out[0].duration_value == 1 and out[0].duration_unit == "dias"


def test_categorias_distintas_se_conservan():
    out = dedupe_preconditions([p("ayuno", 8, "horas"), p("tabaco", 2, "horas")])
    assert {o.category for o in out} == {"ayuno", "tabaco"}


def test_sin_duracion_deduplica_por_texto():
    a = p("recoleccion_muestra", text="Primera orina de la manana")
    b = p("recoleccion_muestra", text="primera orina de la manana ")
    c = p("recoleccion_muestra", text="Aseo genital previo")
    out = dedupe_preconditions([a, b, c])
    assert len(out) == 2


def test_sin_duracion_y_con_duracion_de_misma_categoria_coexisten():
    # p. ej. "solo se permite agua" (sin duracion) junto a "ayuno 8 h".
    out = dedupe_preconditions(
        [p("ayuno", None, None, text="Solo agua"), p("ayuno", 8, "horas")]
    )
    assert len(out) == 2
    assert any(o.duration_value == 8 for o in out)


def test_orden_estable_por_primera_aparicion():
    out = dedupe_preconditions(
        [p("tabaco", 1, "horas"), p("ayuno", 8, "horas"), p("tabaco", 3, "horas")]
    )
    assert [o.category for o in out] == ["tabaco", "ayuno"]
