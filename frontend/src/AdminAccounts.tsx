import { type Dispatch, type SetStateAction, FormEvent, useEffect, useState } from "react";

import { api } from "./api";
import type { Account, Faena } from "./types";

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "No fue posible completar la solicitud.";
}

function FaenaForm({ faena, onSaved, onDeleted, onViewMissions }: {
  faena?: Faena;
  onSaved: (faena: Faena) => void;
  onDeleted?: () => void;
  onViewMissions?: () => void;
}) {
  const [nombre, setNombre] = useState(faena?.nombre ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      onSaved(await (faena ? api.updateFaena(faena.id, nombre) : api.createFaena(nombre)));
      if (!faena) setNombre("");
      setMessage(faena ? "Faena actualizada." : "Faena creada.");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!faena || !window.confirm(`¿Eliminar la faena ${faena.nombre}?`)) return;
    setBusy(true);
    setMessage("");
    try {
      await api.deleteFaena(faena.id);
      onDeleted?.();
    } catch (error) {
      setMessage(errorMessage(error));
      setBusy(false);
    }
  }

  return (
    <form className="card admin-create-account" onSubmit={save}>
      <header><strong>{faena ? faena.nombre : "Crear faena"}</strong></header>
      <div className="admin-create-fields">
        <label><span>Nombre de la faena</span><input required maxLength={120} value={nombre} onChange={(e) => setNombre(e.target.value)} /></label>
      </div>
      <div className="admin-account-actions">
        <button className="button primary" disabled={busy}>{faena ? "Guardar" : "Crear faena"}</button>
        {faena && <>
          <button className="button ghost" type="button" onClick={onViewMissions}>Ver misiones ({faena.misiones})</button>
          <button className="button danger" type="button" disabled={busy || faena.misiones > 0} onClick={remove}>Eliminar faena</button>
        </>}
      </div>
      {message && <p role="status">{message}</p>}
    </form>
  );
}

function UserForm({ faenas, onCreated }: { faenas: Faena[]; onCreated: (user: Account) => void }) {
  const [rol, setRol] = useState<Account["rol"]>("operador");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const password = String(data.get("contrasena"));
    if (password !== data.get("confirmacion")) {
      setMessage("Las contraseñas no coinciden.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const user = await api.createUser(
        String(data.get("nombre")), String(data.get("correo")), password, rol,
        rol === "operador" ? String(data.get("id_faena")) : null,
      );
      onCreated(user);
      form.reset();
      setMessage(`Usuario creado para ${user.correo}.`);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card admin-create-account" onSubmit={create}>
      <header><strong>Crear usuario</strong></header>
      <div className="admin-create-fields">
        <label><span>Nombre</span><input name="nombre" required maxLength={120} /></label>
        <label><span>Correo de acceso</span><input name="correo" type="email" required maxLength={255} /></label>
        <label><span>Rol</span>
          <select value={rol} onChange={(e) => setRol(e.target.value === "admin" ? "admin" : "operador")}>
            <option value="operador">Operador</option>
            <option value="admin">Administrador global</option>
          </select>
        </label>
        {rol === "operador" && (
          <label><span>Faena</span>
            <select name="id_faena" required defaultValue="">
              <option value="">Selecciona una faena</option>
              {faenas.map((faena) => <option key={faena.id} value={faena.id}>{faena.nombre}</option>)}
            </select>
          </label>
        )}
        <label><span>Contraseña inicial</span><input name="contrasena" type="password" required minLength={8} maxLength={128} autoComplete="new-password" /></label>
        <label><span>Confirmar contraseña</span><input name="confirmacion" type="password" required minLength={8} maxLength={128} autoComplete="new-password" /></label>
      </div>
      <button className="button primary" disabled={busy || (rol === "operador" && !faenas.length)}>Crear usuario</button>
      {message && <p role="status">{message}</p>}
    </form>
  );
}

function UserRow({ user, faena }: { user: Account; faena?: Faena }) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function reset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const password = String(data.get("contrasena"));
    if (password !== data.get("confirmacion")) {
      setMessage("Las contraseñas no coinciden.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      await api.resetUserPassword(user.id, password);
      form.reset();
      setMessage("Contraseña actualizada.");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card admin-create-account">
      <header><strong>{user.nombre}</strong></header>
      <span>{user.correo} · {user.rol === "admin" ? "Administrador global" : faena?.nombre ?? "Sin faena asignada"}</span>
      <details>
        <summary>Restablecer contraseña</summary>
        <form className="admin-password-form" onSubmit={reset}>
          <label><span>Nueva contraseña</span><input name="contrasena" type="password" required minLength={8} maxLength={128} autoComplete="new-password" /></label>
          <label><span>Confirmar contraseña</span><input name="confirmacion" type="password" required minLength={8} maxLength={128} autoComplete="new-password" /></label>
          <button className="button ghost" disabled={busy}>Guardar contraseña</button>
          {message && <p role="status">{message}</p>}
        </form>
      </details>
    </article>
  );
}

export default function AdminAccounts({ onViewMissions, faenas, setFaenas }: {
  onViewMissions: (faena: Faena) => void;
  faenas: Faena[];
  setFaenas: Dispatch<SetStateAction<Faena[]>>;
}) {
  const [users, setUsers] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([api.faenas(), api.users()])
      .then(([loadedFaenas, loadedUsers]) => {
        if (!active) return;
        setFaenas(loadedFaenas);
        setUsers(loadedUsers);
      })
      .catch((requestError) => { if (active) setError(errorMessage(requestError)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [setFaenas]);

  function updateFaenas(update: (current: Faena[]) => Faena[]) {
    setFaenas((current) => update(current).sort((a, b) => a.nombre.localeCompare(b.nombre)));
  }

  return (
    <section className="workspace admin-accounts">
      <header className="admin-accounts-title"><h2>Cuentas y accesos</h2></header>
      {loading ? <p>Cargando faenas y usuarios…</p> : error ? <p role="alert">{error}</p> : (
        <>
          <h3>Faenas</h3>
          <FaenaForm onSaved={(faena) => updateFaenas((current) => [...current, faena])} />
          <div className="admin-accounts-grid">
            {faenas.map((faena) => <FaenaForm key={faena.id} faena={faena}
              onSaved={(updated) => updateFaenas((current) => current.map((item) => item.id === updated.id ? updated : item))}
              onDeleted={() => updateFaenas((current) => current.filter((item) => item.id !== faena.id))}
              onViewMissions={() => onViewMissions(faena)} />)}
          </div>
          <h3>Usuarios</h3>
          <UserForm faenas={faenas} onCreated={(user) => setUsers((current) => [...current, user])} />
          <div className="admin-accounts-grid">
            {users.map((user) => <UserRow key={user.id} user={user} faena={faenas.find((faena) => faena.id === user.id_faena)} />)}
          </div>
        </>
      )}
    </section>
  );
}
