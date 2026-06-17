"""
Authentication module for the Dashboard.
Implements secure PBKDF2 HMAC SHA256 password hashing and user management.
"""

import os
from sqlalchemy import select
import bcrypt
from .database import SessionLocal, User, Base, engine

def verify_password(plain_password, hashed_password):
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def get_password_hash(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def init_default_users():
    """Create default admin and rrhh accounts if the users table is empty."""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        user_count = session.query(User).count()
        if user_count == 0:
            # Create Admin
            admin = User(
                username="admin",
                password_hash=get_password_hash("admin"),
                salt="legacy",
                role="admin"
            )
            
            # Create RRHH
            rrhh = User(
                username="rrhh",
                password_hash=get_password_hash("rrhh"),
                salt="legacy",
                role="rrhh"
            )
            
            session.add(admin)
            session.add(rrhh)
            session.commit()
    finally:
        session.close()

def authenticate_user(username: str, password_attempt: str) -> dict:
    """
    Check if username/password are correct.
    Returns {"status": "ok", "role": "..."} or {"status": "error", "message": "..."}
    """
    session = SessionLocal()
    try:
        user = session.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()
        
        if not user:
            return {"status": "error", "message": "Usuario o contraseña incorrectos."}
            
        if not user.is_active:
            return {"status": "error", "message": "Cuenta desactivada. Contacte al administrador."}
            
        # Compatibilidad con contraseñas antiguas (PBKDF2) si hiciera falta:
        # Pero como el requirement es cambiar a bcrypt, solo checaremos bcrypt
        # Si queremos retrocompatibilidad, la dejamos fuera o hacemos una validacion.
        # Por simplicidad asuminos que se resetearan o que verify lo maneja si usaramos multiples esquemas.
        
        # En caso de que haya hashes viejos (sin el prefijo $2b$), fallara, por lo cual
        # debemos re-crearlos o avisar. Por ahora comprobemos bcrypt.
        try:
            if verify_password(password_attempt, user.password_hash):
                return {"status": "ok", "role": user.role}
        except ValueError:
            # Si el hash es viejo PBKDF2 y no se puede leer
            import hashlib, binascii
            try:
                salt_bytes = binascii.unhexlify(user.salt)
                old_hash = binascii.hexlify(hashlib.pbkdf2_hmac("sha256", password_attempt.encode('utf-8'), salt_bytes, 100000)).decode('ascii')
                if old_hash == user.password_hash:
                    # Migrar a bcrypt de una vez
                    user.password_hash = get_password_hash(password_attempt)
                    session.commit()
                    return {"status": "ok", "role": user.role}
            except Exception:
                pass
                
        return {"status": "error", "message": "Usuario o contraseña incorrectos."}
    finally:
        session.close()

def change_password(username: str, old_password: str, new_password: str) -> dict:
    """Allows a user to change their own password."""
    session = SessionLocal()
    try:
        user = session.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()
        
        if not user:
            return {"status": "error", "message": "Usuario no encontrado."}
            
        # Verify old
        valid = False
        try:
            valid = verify_password(old_password, user.password_hash)
        except ValueError:
            import hashlib, binascii
            try:
                salt_bytes = binascii.unhexlify(user.salt)
                old_hash = binascii.hexlify(hashlib.pbkdf2_hmac("sha256", old_password.encode('utf-8'), salt_bytes, 100000)).decode('ascii')
                valid = (old_hash == user.password_hash)
            except Exception:
                valid = False
                
        if not valid:
            return {"status": "error", "message": "La contraseña actual es incorrecta."}
            
        # Hash new
        user.salt = "bcrypt"
        user.password_hash = get_password_hash(new_password)
        session.commit()
        
        return {"status": "ok", "message": "Contraseña actualizada exitosamente."}
    except Exception as e:
        session.rollback()
        return {"status": "error", "message": f"Error interno: {e}"}
    finally:
        session.close()

def get_users() -> list:
    """Returns a list of users without password hashes."""
    session = SessionLocal()
    try:
        users = session.execute(select(User)).scalars().all()
        return [{"username": u.username, "role": u.role, "is_active": u.is_active} for u in users]
    finally:
        session.close()

def create_user(username: str, password: str, role: str) -> dict:
    """Creates a new user."""
    session = SessionLocal()
    try:
        existing = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if existing:
            return {"status": "error", "message": "El usuario ya existe."}
            
        new_user = User(
            username=username,
            password_hash=get_password_hash(password),
            salt="bcrypt",
            role=role
        )
        session.add(new_user)
        session.commit()
        return {"status": "ok"}
    except Exception as e:
        session.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        session.close()

def update_user_role(username: str, new_role: str) -> dict:
    """Updates a user's role."""
    session = SessionLocal()
    try:
        user = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not user:
            return {"status": "error", "message": "Usuario no encontrado."}
        user.role = new_role
        session.commit()
        return {"status": "ok"}
    except Exception as e:
        session.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        session.close()

def toggle_user_active(username: str, is_active: bool) -> dict:
    """Activates or deactivates a user instead of deleting them."""
    session = SessionLocal()
    try:
        user = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not user:
            return {"status": "error", "message": "Usuario no encontrado."}
        user.is_active = is_active
        session.commit()
        return {"status": "ok"}
    except Exception as e:
        session.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        session.close()
