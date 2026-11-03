"""
Which students a lecturer may see and act on.

The only relationship OralIQ has between a lecturer and a student is one the student creates: they
open the lecturer's exam link and submit an answer. That — at least one submission to one of the
lecturer's own questions — is what grants access here. An assignment does not: assigning used to
accept any student id and then counted as a link, so a lecturer (anyone can sign up as one) could
walk ids, "assign" them, and read back every student's e-mail. Existing assignments are kept and
still show up for the student; they simply no longer open the student's data to the lecturer.

Admins keep platform-wide access, as before. HR accounts follow the lecturer rule, as before.
"""
from sqlalchemy.orm import Query, Session

from app.models.exam_submission import ExamSubmission
from app.models.question import Question
from app.models.user import User


def is_platform_admin(user: User) -> bool:
    return user.role == "admin"


def related_student_ids(db: Session, lecturer: User) -> Query:
    """Subquery: ids of students who submitted to one of this lecturer's questions."""
    own_questions = db.query(Question.id).filter(Question.creator_id == lecturer.id)
    return (
        db.query(ExamSubmission.student_id)
        .filter(ExamSubmission.question_id.in_(own_questions), ExamSubmission.student_id.isnot(None))
        .distinct()
    )


def accessible_students(db: Session, lecturer: User) -> Query:
    q = db.query(User).filter(User.role == "student")
    if not is_platform_admin(lecturer):
        q = q.filter(User.id.in_(related_student_ids(db, lecturer)))
    return q


def can_access_student(db: Session, lecturer: User, student_id: int) -> bool:
    """True only for a student account this lecturer is related to (any student for an admin).
    Callers answer 'not found' otherwise, the same as for an id that doesn't exist."""
    return accessible_students(db, lecturer).filter(User.id == student_id).first() is not None
