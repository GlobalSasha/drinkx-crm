"""embed.js generator — Sprint 2.2 G2.

Returns a self-contained JavaScript blob that drops a form onto any
landing page. No dependencies, no framework, ~80 lines of plain DOM.

User-controlled content (form name, labels, slug) is injected via
`json.dumps()` so JS string escapes are correct — we don't paste raw
strings into the JS source.
"""
from __future__ import annotations

import json

from app.forms.models import WebForm


def generate_embed_js(form: WebForm, *, api_base_url: str) -> str:
    """Return the body of /api/public/forms/{slug}/embed.js for the
    given form. Caller sets Content-Type + cache headers."""
    config = {
        "slug": form.slug,
        "name": form.name,
        "submitUrl": (
            api_base_url.rstrip("/")
            + f"/api/public/forms/{form.slug}/submit"
        ),
        "redirectUrl": form.redirect_url,
        "fields": list(form.fields_json or []),
    }
    config_json = json.dumps(config, ensure_ascii=False)

    return f"""(function() {{
  var CONFIG = {config_json};
  if (window.__drinkxFormLoaded_{_safe_id(form.slug)}) return;
  window.__drinkxFormLoaded_{_safe_id(form.slug)} = true;

  var script = document.currentScript;
  var mountId = "drinkx-form-" + CONFIG.slug;
  var mount = document.getElementById(mountId)
    || (script ? script.parentElement : document.body);

  var form = document.createElement("form");
  form.className = "drinkx-form";
  form.setAttribute("novalidate", "novalidate");
  form.style.cssText = "display:flex;flex-direction:column;gap:10px;font-family:inherit;";

  CONFIG.fields.forEach(function(field) {{
    var wrap = document.createElement("label");
    wrap.style.cssText = "display:flex;flex-direction:column;gap:4px;font-size:13px;";
    var labelText = document.createElement("span");
    labelText.textContent = field.label + (field.required ? " *" : "");
    wrap.appendChild(labelText);

    var input;
    if (field.type === "textarea") {{
      input = document.createElement("textarea");
      input.rows = 4;
    }} else if (field.type === "select") {{
      input = document.createElement("select");
      var blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "—";
      input.appendChild(blank);
      (field.options || []).forEach(function(opt) {{
        var o = document.createElement("option");
        o.value = opt;
        o.textContent = opt;
        input.appendChild(o);
      }});
    }} else {{
      input = document.createElement("input");
      input.type = field.type === "email" ? "email"
        : field.type === "phone" ? "tel" : "text";
    }}
    input.name = field.key;
    if (field.required) input.required = true;
    input.style.cssText = "padding:8px 10px;border:1px solid #d0d4d8;border-radius:8px;font:inherit;";
    wrap.appendChild(input);
    form.appendChild(wrap);
  }});

  var submit = document.createElement("button");
  submit.type = "submit";
  submit.textContent = "Отправить";
  submit.style.cssText = "padding:10px 16px;border:0;border-radius:9999px;background:#111;color:#fff;font:inherit;font-weight:600;cursor:pointer;align-self:flex-start;";
  form.appendChild(submit);

  var status = document.createElement("div");
  status.className = "drinkx-form-status";
  status.style.cssText = "min-height:18px;font-size:12px;color:#444;";
  form.appendChild(status);

  function getUtm() {{
    var u = {{}};
    try {{
      var p = new URLSearchParams(window.location.search);
      ["utm_source","utm_medium","utm_campaign","utm_content","utm_term"]
        .forEach(function(k) {{ if (p.get(k)) u[k] = p.get(k); }});
    }} catch (e) {{}}
    return u;
  }}

  form.addEventListener("submit", function(e) {{
    e.preventDefault();
    submit.disabled = true;
    status.textContent = "Отправляем…";
    status.style.color = "#444";

    var payload = {{}};
    new FormData(form).forEach(function(v, k) {{ payload[k] = v; }});
    var utm = getUtm();
    Object.keys(utm).forEach(function(k) {{ payload[k] = utm[k]; }});

    fetch(CONFIG.submitUrl, {{
      method: "POST",
      mode: "cors",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload),
    }})
      .then(function(r) {{ return r.json().then(function(d) {{ return {{ status: r.status, body: d }}; }}); }})
      .then(function(res) {{
        if (res.status === 200 && res.body && res.body.ok) {{
          if (res.body.redirect) {{ window.location.href = res.body.redirect; return; }}
          status.textContent = "Спасибо! Заявка отправлена.";
          status.style.color = "#0a7d2c";
          form.reset();
        }} else if (res.status === 429) {{
          status.textContent = "Слишком много попыток. Попробуйте через минуту.";
          status.style.color = "#a13";
        }} else if (res.status === 410) {{
          status.textContent = "Форма больше не принимает заявки.";
          status.style.color = "#a13";
        }} else {{
          status.textContent =
            (res.body && res.body.detail) || "Не удалось отправить. Попробуйте позже.";
          status.style.color = "#a13";
        }}
      }})
      .catch(function() {{
        status.textContent = "Сеть недоступна. Проверьте соединение.";
        status.style.color = "#a13";
      }})
      .finally(function() {{ submit.disabled = false; }});
  }});

  mount.appendChild(form);
}})();
"""


def _safe_id(slug: str) -> str:
    """Slug-derived identifier safe inside a JS variable name. Replaces
    hyphens with underscores so the IIFE-once guard
    (`window.__drinkxFormLoaded_<id>`) is a valid JS identifier."""
    return "".join(c if c.isalnum() else "_" for c in slug)


__all__ = ["generate_embed_js"]
