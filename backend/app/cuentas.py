"""Administración de usuarios. Ejecutar con python -m app.cuentas --help."""

import argparse
import getpass
import sys

from sqlmodel import Session, select

from app.database import engine
from app.models import Faena, Usuario
from app.services.passwords import hash_password


def ask_password() -> str:
    while True:
        password = getpass.getpass("Contraseña (mínimo 8 caracteres): ")
        if not 8 <= len(password) <= 128:
            print("La contraseña debe tener entre 8 y 128 caracteres.")
        elif getpass.getpass("Repite la contraseña: ") == password:
            return password
        else:
            print("Las contraseñas no coinciden.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Administración de usuarios de NeumaVision")
    commands = parser.add_subparsers(dest="accion", required=True)
    create = commands.add_parser("crear")
    create.add_argument("--nombre", required=True)
    create.add_argument("--correo", required=True)
    assignment = create.add_mutually_exclusive_group(required=True)
    assignment.add_argument("--admin", action="store_true")
    assignment.add_argument("--faena", metavar="ID")
    reset = commands.add_parser("contrasena")
    reset.add_argument("--correo", required=True)
    commands.add_parser("listar")
    args = parser.parse_args()

    with Session(engine) as session:
        if args.accion == "listar":
            for user in session.exec(select(Usuario).order_by(Usuario.nombre)):
                print(f"{user.nombre} <{user.correo}> · {user.rol}")
            return

        correo = args.correo.strip().lower()
        user = session.exec(select(Usuario).where(Usuario.correo == correo)).first()
        if args.accion == "crear":
            if user:
                sys.exit("Ya existe una cuenta con ese correo.")
            if args.faena and session.get(Faena, args.faena) is None:
                sys.exit("Faena no encontrada.")
            user = Usuario(
                nombre=args.nombre.strip(), correo=correo, rol="admin" if args.admin else "operador",
                id_faena=args.faena,
            )
            session.add(user)
        elif user is None:
            sys.exit("Usuario no encontrado.")

        user.hash_contrasena = hash_password(ask_password())
        session.commit()
        print(f"Cuenta guardada: {user.correo} · {user.rol}")


if __name__ == "__main__":
    main()
