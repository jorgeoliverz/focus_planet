"""Mini interfaz de prueba del coach semanal. Ejecuta: python app.py  ->  http://localhost:8000"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from focus_planet.coach import CoachError, get_weekly_coaching

PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Focus Planet · Coach</title>
<style>
 body{font-family:system-ui,sans-serif;background:#0b1026;color:#e8ecff;max-width:520px;margin:0 auto;padding:24px 16px}
 h1{font-size:1.4rem} label{display:block;margin:12px 0 4px;font-size:.9rem;color:#aab3e0}
 input,select{width:100%;padding:8px;border-radius:8px;border:1px solid #33407a;background:#141b3d;color:inherit;box-sizing:border-box}
 button{margin-top:16px;width:100%;padding:12px;border:0;border-radius:8px;background:#6c7bff;color:#fff;font-size:1rem;cursor:pointer}
 button:disabled{opacity:.6}
 #out{margin-top:20px;padding:16px;border-radius:12px;background:#141b3d;display:none}
 #out.error{background:#4a1d2b} li{margin:4px 0} h3{margin:14px 0 4px;font-size:1rem}
</style></head><body>
<h1>🪐 Tu compañero astronauta</h1>
<form id="f">
 <label>Minutos concentrado esta semana<input name="total_minutes" type="number" min="0" value="300"></label>
 <label>Sesiones completadas<input name="sessions" type="number" min="0" value="8"></label>
 <label>Sesiones abandonadas<input name="abandoned_sessions" type="number" min="0" value="1"></label>
 <label>Mejor día<select name="best_day"><option value="">(ninguno)</option>
  <option>lunes</option><option>martes</option><option>miércoles</option><option selected>jueves</option>
  <option>viernes</option><option>sábado</option><option>domingo</option></select></label>
 <label>Planetas construidos<input name="planets_built" type="number" min="0" value="1"></label>
 <button id="b">Hablar con mi compañero</button>
</form>
<div id="out"></div>
<script>
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const list=a=>a.length?"<ul>"+a.map(x=>"<li>"+esc(x)+"</li>").join("")+"</ul>":"<p>—</p>";
f.onsubmit=async e=>{
 e.preventDefault(); b.disabled=true; b.textContent="Contactando con la nave…";
 const d=Object.fromEntries(new FormData(f));
 for(const k of ["total_minutes","sessions","abandoned_sessions","planets_built"]) d[k]=Number(d[k]);
 d.best_day=d.best_day||null;
 try{
  const r=await fetch("/coach",{method:"POST",body:JSON.stringify(d)}); const j=await r.json();
  out.style.display="block"; out.className=r.ok?"":"error";
  out.innerHTML=r.ok?`<p>${esc(j.summary)}</p><h3>Logros</h3>${list(j.achievements)}<h3>Para mejorar</h3>${list(j.improvements)}<h3>Objetivo semanal</h3><p>${j.next_goal_minutes} min</p>`:`<p>⚠️ ${esc(j.error)}</p>`;
 }catch{out.style.display="block";out.className="error";out.textContent="⚠️ No se pudo conectar con el servidor.";}
 b.disabled=false; b.textContent="Hablar con mi compañero";
};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, ctype="application/json"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE, "text/html")
        else:
            self._send(404, json.dumps({"error": "No encontrado"}))

    def do_POST(self):
        if self.path != "/coach":
            return self._send(404, json.dumps({"error": "No encontrado"}))
        try:
            length = int(self.headers.get("Content-Length", 0))
            stats = json.loads(self.rfile.read(length))
            result = get_weekly_coaching(stats)
            self._send(200, result.model_dump_json())
        except CoachError as e:
            status = 429 if e.code == "rate_limit" else 502
            self._send(status, json.dumps({"error": e.user_message}))
        except (ValueError, TypeError):
            self._send(400, json.dumps({"error": "Datos no válidos."}))


if __name__ == "__main__":
    print("Abre http://localhost:8000")
    HTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
