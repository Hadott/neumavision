import { Eye, EyeOff, LoaderCircle, Mail, Save, Shield, Users, KeyRound, AlertTriangle, UserPlus } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { api } from "./api";
import type { Account } from "./types";

function AccountCard({
  account,
  onUpdated,
  onViewMissions
}: {
  account: Account;
  onUpdated: (account: Account) => void;
  onViewMissions: (account: Account) => void;
}) {
  const [nombre, setNombre] = useState(account.nombre);
  const [correo, setCorreo] = useState(account.correo);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState<"profile" | "password" | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setBusy("profile");
    setError("");
    setSuccess("");
    try {
      onUpdated(await api.updateFaena(account.id, nombre, correo));
      setSuccess("Datos de la cuenta actualizados.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No se pudo actualizar la cuenta.");
    } finally {
      setBusy(null);
    }
  }

  async function resetPassword(event: FormEvent) {
    event.preventDefault();
    if (password !== confirmPassword) {
      setError("Las contraseñas no coinciden.");
      return;
    }
    setBusy("password");
    setError("");
    setSuccess("");
    try {
      await api.resetFaenaPassword(account.id, password);
      setPassword("");
      setConfirmPassword("");
      setSuccess("Contraseña restablecida. Comunícala al usuario por un canal privado.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No se pudo restablecer la contraseña.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <article className="card admin-account-card">
      <header className="admin-account-header">
        <span className="admin-account-icon"><Users size={17} /></span>
        <div>
          <strong>{account.nombre}</strong>
          <span className="admin-account-role"><Shield size={12} /> {account.rol === "admin" ? "Administrador" : "Faena"}</span>
        </div>
      </header>

      <form className="admin-account-form" onSubmit={saveProfile}>
        <label>
          <span>Nombre</span>
          <input required maxLength={120} value={nombre} onChange={(event) => setNombre(event.target.value)} />
        </label>
        <label>
          <span>Correo electrónico</span>
          <input required type="email" maxLength={255} value={correo} onChange={(event) => setCorreo(event.target.value)} />
        </label>
        <div className="admin-account-actions">
          <button className="button primary" type="submit" disabled={busy !== null}>
            {busy === "profile" ? <LoaderCircle className="spin" size={14} /> : <Save size={14} />}
            Guardar datos
          </button>
          <button className="button ghost" type="button" onClick={() => onViewMissions(account)}>
            Ver {account.misiones ?? 0} misiones
          </button>
        </div>
      </form>

      <form className="admin-password-form" onSubmit={resetPassword}>
        <strong><KeyRound size={14} /> Restablecer contraseña</strong>
        <p>La contraseña anterior no se puede consultar. Asigna una nueva de al menos 8 caracteres.</p>
        <label>
          <span>Nueva contraseña temporal</span>
          <div className="admin-password-input">
            <input
              required
              minLength={8}
              maxLength={128}
              autoComplete="new-password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <button type="button" aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"} onClick={() => setShowPassword((value) => !value)}>
              {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
        </label>
        <label>
          <span>Confirmar nueva contraseña</span>
          <input
            required
            minLength={8}
            maxLength={128}
            autoComplete="new-password"
            type={showPassword ? "text" : "password"}
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />
        </label>
        <button className="button ghost" type="submit" disabled={busy !== null}>
          {busy === "password" ? <LoaderCircle className="spin" size={14} /> : <KeyRound size={14} />}
          Asignar contraseña nueva
        </button>
      </form>
      {error && <div className="admin-account-message error"><AlertTriangle size={14} />{error}</div>}
      {success && <div className="admin-account-message success"><Mail size={14} />{success}</div>}
    </article>
  );
}

export default function AdminAccounts({ onViewMissions }: { onViewMissions: (account: Account) => void }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.adminFaenas()
      .then(setAccounts)
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "No se pudieron cargar las cuentas."))
      .finally(() => setLoading(false));
  }, []);

  function updateAccount(updated: Account) {
    setAccounts((current) => current.map((account) => account.id === updated.id ? { ...account, ...updated } : account));
  }

  function addAccount(created: Account) {
    setAccounts((current) => [...current, created].sort((a, b) => a.nombre.localeCompare(b.nombre)));
  }

  return (
    <section className="workspace admin-accounts">
      <header className="admin-accounts-title">
        <div><span className="overline">Administración</span><h2>Cuentas y accesos</h2></div>
        <p>Crea cuentas de faena, actualiza sus datos, revisa las misiones asignadas o establece una contraseña nueva.</p>
      </header>
      <div className="admin-security-note">
        <Shield size={16} />
        Las contraseñas se guardan como hash y no se pueden recuperar. Al crear o restablecer una, entrégala por un canal privado.
      </div>
      {error && <div className="admin-account-message error"><AlertTriangle size={14} />{error}</div>}
      {loading ? (
        <div className="admin-accounts-loading"><LoaderCircle className="spin" size={18} /> Cargando cuentas…</div>
      ) : (
        <>
          <CreateAccountForm onCreated={addAccount} />
          {accounts.length ? (
            <div className="admin-accounts-grid">
              {accounts.map((account) => (
                <AccountCard key={account.id} account={account} onUpdated={updateAccount} onViewMissions={onViewMissions} />
              ))}
            </div>
          ) : !error ? (
            <div className="admin-accounts-loading">Todavía no hay cuentas; crea la primera con el formulario anterior.</div>
          ) : null}
        </>
      )}
    </section>
  );
}

function CreateAccountForm({ onCreated }: { onCreated: (account: Account) => void }) {
  const [nombre, setNombre] = useState("");
  const [correo, setCorreo] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function createAccount(event: FormEvent) {
    event.preventDefault();
    if (password !== confirmPassword) {
      setError("Las contraseñas no coinciden.");
      return;
    }

    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const created = await api.createFaena(nombre, correo, password);
      onCreated(created);
      setNombre("");
      setCorreo("");
      setPassword("");
      setConfirmPassword("");
      setSuccess(`Cuenta creada para ${created.correo}. Comunica la contraseña por un canal privado.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No se pudo crear la cuenta.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card admin-create-account" onSubmit={createAccount}>
      <header><span className="admin-account-icon"><UserPlus size={17} /></span><div><strong>Crear cuenta de faena</strong><span>Se asignará el rol de usuario de faena.</span></div></header>
      <div className="admin-create-fields">
        <label><span>Nombre de la faena</span><input required minLength={1} maxLength={120} value={nombre} onChange={(event) => setNombre(event.target.value)} /></label>
        <label><span>Correo de acceso</span><input required type="email" maxLength={255} value={correo} onChange={(event) => setCorreo(event.target.value)} /></label>
        <label>
          <span>Contraseña inicial (mínimo 8 caracteres)</span>
          <div className="admin-password-input">
            <input required minLength={8} maxLength={128} autoComplete="new-password" type={showPassword ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} />
            <button type="button" aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"} onClick={() => setShowPassword((value) => !value)}>
              {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
        </label>
        <label><span>Confirmar contraseña</span><input required minLength={8} maxLength={128} autoComplete="new-password" type={showPassword ? "text" : "password"} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} /></label>
      </div>
      <div className="admin-create-submit">
        <button className="button primary" type="submit" disabled={busy}>
          {busy ? <LoaderCircle className="spin" size={14} /> : <UserPlus size={14} />} Crear cuenta
        </button>
      </div>
      {error && <div className="admin-account-message error"><AlertTriangle size={14} />{error}</div>}
      {success && <div className="admin-account-message success"><Mail size={14} />{success}</div>}
    </form>
  );
}
