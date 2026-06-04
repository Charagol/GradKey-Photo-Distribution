"""学生服务 — 学生实体的 CRUD 与密钥生成。

密钥生成排除易混淆字符: 0, O, 1, I。
"""

import secrets
from typing import Sequence

from sqlalchemy.orm import Session

from app.models.student import Student

#: 密钥可用字符集（排除 0, O, 1, I），共 30 个字符。
_KEY_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

#: 密钥默认长度。
_KEY_LENGTH = 6


def generate_secret_key(length: int = _KEY_LENGTH) -> str:
    """生成学生个人密钥。

    使用 secrets 模块确保密码学安全随机性。
    字符集排除 0, O, 1, I 以避免视觉混淆。

    Args:
        length: 密钥长度，默认 6。

    Returns:
        str: 指定位数的随机密钥。
    """
    return "".join(secrets.choice(_KEY_CHARS) for _ in range(length))


def create_student(db: Session, name: str) -> Student:
    """创建学生并自动生成个人密钥。

    Args:
        db: 数据库会话。
        name: 学生姓名。

    Returns:
        Student: 新创建的学生对象（已刷新含 id 和密钥）。
    """
    student = Student(name=name, secret_key=generate_secret_key())
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


def get_student(db: Session, student_id: int) -> Student | None:
    """按 ID 查找学生。

    Args:
        db: 数据库会话。
        student_id: 学生主键。

    Returns:
        Student | None: 找到的学生或 None。
    """
    return db.query(Student).filter(Student.id == student_id).first()


def list_students(db: Session) -> Sequence[Student]:
    """列出所有学生，按创建时间倒序。

    Args:
        db: 数据库会话。

    Returns:
        Sequence[Student]: 学生列表。
    """
    return db.query(Student).order_by(Student.created_at.desc()).all()


def update_student(db: Session, student_id: int, name: str) -> Student:
    """更新学生姓名。

    Args:
        db: 数据库会话。
        student_id: 学生主键。
        name: 新姓名。

    Returns:
        Student: 更新后的学生对象。
    """
    student = db.query(Student).filter(Student.id == student_id).first()
    if student is None:
        raise ValueError(f"Student id={student_id} not found")
    student.name = name
    db.commit()
    db.refresh(student)
    return student


def delete_student(db: Session, student_id: int) -> None:
    """删除学生。

    Args:
        db: 数据库会话。
        student_id: 学生主键。
    """
    student = db.query(Student).filter(Student.id == student_id).first()
    if student is None:
        raise ValueError(f"Student id={student_id} not found")
    db.delete(student)
    db.commit()


def regenerate_key(db: Session, student_id: int) -> str:
    """重置学生个人密钥。

    Args:
        db: 数据库会话。
        student_id: 学生主键。

    Returns:
        str: 新生成的密钥。
    """
    student = db.query(Student).filter(Student.id == student_id).first()
    if student is None:
        raise ValueError(f"Student id={student_id} not found")
    new_key = generate_secret_key()
    student.secret_key = new_key
    db.commit()
    db.refresh(student)
    return new_key
