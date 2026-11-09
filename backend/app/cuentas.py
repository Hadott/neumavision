"""Administración de cuentas desde la terminal.

Uso (desde la carpeta backend, con el entorno virtual activado):

  python -m app.cuentas crear --nombre "Compañía Minera Zaldívar" --correo zaldivar@ejemplo.cl
  python -m app.cuentas crear --nombre "NeumaDiesel" --correo admin@neumadiesel.cl --admin
  python -m app.cuentas contrasena --correo zaldivar@ejemplo.cl
  python -m app.cuentas rol --correo neumavision@neumadiesel.com --admin
  python -m app.cuentas mover-misiones --desde neumavision@neumadiesel.com --hacia zaldivar@ejemplo.cl
  python -m app.cuentas renombrar --correo neumavision@neumadiesel.com --nombre "NeumaDiesel"
  python -m app.cuentas listar

La contraseña se pide por teclado (no queda en el historial de la terminal).
"""

import argparse
import getpass
import sys

from sqlmodel import Session, select

from app.database import engine, initialize_database
from app.models import Faena, Mision
from app.services.passwords import hash_password


def _ask_password() -> str:
    while True:
        first = getpass.getpass("Contraseña (mínimo 8 caracteres): ")
        if len(first) < 8:
            print("La contraseña debe tener al menos 8 caracteres.")
            continue
        if getpass.getpass("Repite la contraseña: ") != first:
            print("Las contraseñas no coinciden.")
            continue
        return first


def _find(session: Session, correo: str) -> Faena:
    faena = session.exec(select(Faena).where(Faena.correo == correo.strip().lower())).first()
    if faena is None:
        sys.exit(f"No existe una cuenta con el correo {correo}.")
    return faena


def main() -> None:
    parser = argparse.ArgumentParser(description="Administración de cuentas de NeumaVision")
    sub = parser.add_subparsers(dest="accion", required=True)
    crear = sub.add_parser("crear", help="Crear una cuenta de faena o de administrador")
    crear.add_argument("--nombre", required=True)
    crear.add_argument("--correo", required=True)
    crear.add_argument("--admin", action="store_true", help="La cuenta podrá ver todas las faenas")
    contrasena = sub.add_parser("contrasena", help="Cambiar la contraseña de una cuenta")
    contrasena.add_argument("--correo", required=True)
    rol = sub.add_parser("rol", help="Cambiar el rol de una cuenta")
    rol.add_argument("--correo", required=True)
    rol.add_argument("--admin", action="store_true", help="Sin esta opción la cuenta queda como faena")
    mover = sub.add_parser("mover-misiones", help="Traspasar todas las misiones de una cuenta a otra")
    mover.add_argument("--desde", required=True)
    mover.add_argument("--hacia", required=True)
    renombrar = sub.add_parser("renombrar", help="Cambiar el nombre visible de una cuenta")
    renombrar.add_argument("--correo", required=True)
    renombrar.add_argument("--nombre", required=True)
    sub.add_parser("listar", help="Listar las cuentas existentes")
    args = parser.parse_args()

    initialize_database()
    with Session(engine) as session:
        if args.accion == "crear":
            correo = args.correo.strip().lower()
            if session.exec(select(Faena).where(Faena.correo == correo)).first():
                sys.exit(f"Ya existe una cuenta con el correo {correo}.")
            faena = Faena(
                nombre=args.nombre.strip(),
                correo=correo,
                hash_contrasena=hash_password(_ask_password()),
                rol="admin" if args.admin else "faena",
            )
            session.add(faena)
            session.commit()
            print(f"Cuenta creada: {faena.nombre} <{faena.correo}> · rol {faena.rol}")
        elif args.accion == "contrasena":
            faena = _find(session, args.correo)
            faena.hash_contrasena = hash_password(_ask_password())
            session.add(faena)
            session.commit()
            print(f"Contraseña actualizada para {faena.correo}.")
        elif args.accion == "rol":
            faena = _find(session, args.correo)
            faena.rol = "admin" if args.admin else "faena"
            session.add(faena)
            session.commit()
            print(f"{faena.correo} ahora tiene rol {faena.rol}.")
        elif args.accion == "mover-misiones":
            origen = _find(session, args.desde)
            destino = _find(session, args.hacia)
            misiones = session.exec(select(Mision).where(Mision.id_faena == origen.id_faena)).all()
            for mision in misiones:
                mision.id_faena = destino.id_faena
                session.add(mision)
            session.commit()
            print(f"{len(misiones)} misiones traspasadas de {origen.nombre} a {destino.nombre}.")
        elif args.accion == "renombrar":
            faena = _find(session, args.correo)
            faena.nombre = args.nombre.strip()
            session.add(faena)
            session.commit()
            print(f"{faena.correo} ahora se llama {faena.nombre}.")
        elif args.accion == "listar":
            for faena in session.exec(select(Faena).order_by(Faena.nombre)).all():
                total = len(session.exec(select(Mision).where(Mision.id_faena == faena.id_faena)).all())
                print(f"{faena.nombre:<35} {faena.correo:<32} rol={faena.rol or 'faena':<6} misiones={total}")


if __name__ == "__main__":
    main()
