import { LoaderCircle } from "lucide-react";
import { motion } from "framer-motion";
import { FormEvent, useState } from "react";

import { api } from "./api";
import loginBg from "./assets/login-bg.jpg";
import logoIcon from "./assets/logo-icon-dark.png";
import type { Session } from "./types";

export default function Login({ onLogin }: { onLogin: (session: Session) => void }) {
  const [correo, setCorreo] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogin(await api.login(correo, contrasena));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible iniciar sesión.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <motion.div
          className="login-brand-panel"
          initial={{ opacity: 0, x: -24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
          style={{
            backgroundImage: `linear-gradient(180deg, rgba(11,12,14,.55) 0%, rgba(11,12,14,.35) 40%, rgba(11,12,14,.92) 100%), url(${loginBg})`
          }}
        >
          <div className="brand">
            <span className="brand-icon"><img src={logoIcon} alt="NeumaDiesel" /></span>
            <span><strong>NeumaVision</strong><small>NeumaDiesel</small></span>
          </div>
          <div>
            <h1>Los caminos de tu faena, vistos desde el dron.</h1>
            <p>Rocas sobre la pista y ancho para dos CAEX, foto por foto, listos para el informe de mantención.</p>
          </div>
        </motion.div>

        <motion.form
          className="login-form"
          onSubmit={submit}
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.12, ease: "easeOut" }}
        >
                    <h2>Inicia sesión</h2>
          <p className="login-sub">Ingresa con las credenciales entregadas por NeumaDiesel.</p>

          {error && <div className="login-error">{error}</div>}

          <label>
            <span>Correo electrónico</span>
            <div className="login-input">
              <input type="email" autoComplete="username" required value={correo} onChange={(event) => setCorreo(event.target.value)} placeholder="nombre@empresa.cl" />
            </div>
          </label>
          <label>
            <span>Contraseña</span>
            <div className="login-input">
              <input type={showPassword ? "text" : "password"} autoComplete="current-password" required value={contrasena} onChange={(event) => setContrasena(event.target.value)} />
              <button type="button" onClick={() => setShowPassword((value) => !value)}>{showPassword ? "Ocultar" : "Mostrar"}</button>
            </div>
          </label>

          <button className="button primary full large" type="submit" disabled={busy}>
            {busy ? <LoaderCircle className="spin" size={16} /> : "Ingresar"}
          </button>
          <p className="login-help">¿Olvidaste tu contraseña? Contacta al administrador de NeumaDiesel.</p>
        </motion.form>
      </section>
    </main>
  );
}
