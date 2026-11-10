from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1]/'streamlit_app.py'


def widget(widgets,label):
    return next(item for item in widgets if item.label == label)


def test_variant_point_and_rejected_point_have_clear_outcomes():
    app = AppTest.from_file(str(APP),default_timeout=30).run()
    widget(app.selectbox,'Configuration CFD').select('sigma_1p7').run()
    curves = widget(app.checkbox,'Generer la simulation interpolee sur 360°')
    assert curves.disabled and not curves.value
    app.radio[0].set_value("Evaluation d'un point").run()
    widget(app.number_input,'Vitesse cible [kn]').set_value(10/core_knot_to_ms()).run()
    widget(app.number_input,'Lambda impose').set_value(1.1)
    widget(app.number_input,'Bmax impose [deg]').set_value(17.5)
    app.button[0].click().run()
    assert not app.exception and not app.error
    assert len(app.metric) == 6
    assert any('calcul CFD convergé' in item.value for item in app.info)
    # Known bad V30 sigma run.1102: no metrics from this case may be displayed.
    widget(app.number_input,'Vitesse cible [kn]').set_value(30/core_knot_to_ms())
    widget(app.number_input,'Lambda impose').set_value(.8)
    widget(app.number_input,'Bmax impose [deg]').set_value(25)
    app.run()
    assert not app.exception
    assert any('exclu' in item.value for item in app.error)
    assert not app.metric


def core_knot_to_ms():
    return .514444


def test_optimization_and_reference_workflows():
    app = AppTest.from_file(str(APP),default_timeout=30).run()
    widget(app.selectbox,'Configuration CFD').select('combined_1p7').run()
    app.button[0].click().run()
    assert not app.exception and not app.error
    assert any(item.label == 'Lambda opt' for item in app.metric)
    assert any('Qualité' in item.value for item in app.info)
    # Switching back also restores the existing reference evaluation.
    widget(app.selectbox,'Configuration CFD').select('reference')
    app.radio[0].set_value("Evaluation d'un point")
    app.run()
    widget(app.checkbox,'Generer la simulation interpolee sur 360°').uncheck().run()
    assert not app.exception and not app.error
    assert len(app.metric) == 6
    assert not any('Qualité' in item.value for item in app.info)
