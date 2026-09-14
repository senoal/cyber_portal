"""
=====================================================
File Helper
Enterprise File Management Utility

Author : IT Security Department
=====================================================
"""

import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename


# =====================================================
# CONFIGURATION
# =====================================================

ALLOWED_EXTENSIONS = {

    "pdf",

    "doc",
    "docx",

    "xls",
    "xlsx",
    "csv",

    "txt",

    "png",
    "jpg",
    "jpeg",
    "gif"

}

MAX_FILE_SIZE = 10 * 1024 * 1024      # 10 MB


# =====================================================
# PROJECT ROOT
# =====================================================

def get_project_root():
    """
    Return project root directory.

    Example:
    C:/Project/Sec_App
    """

    return os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            ".."
        )
    )


# =====================================================
# CHECK EXTENSION
# =====================================================

def allowed_file(filename):

    if not filename:
        return False

    if "." not in filename:
        return False

    ext = filename.rsplit(".", 1)[1].lower()

    return ext in ALLOWED_EXTENSIONS


# =====================================================
# GET EXTENSION
# =====================================================

def get_extension(filename):

    if "." not in filename:
        return ""

    return filename.rsplit(".", 1)[1].lower()


# =====================================================
# SAFE ORIGINAL NAME
# =====================================================

def get_original_filename(file):

    return secure_filename(file.filename)


# =====================================================
# GENERATE UNIQUE FILE NAME
# =====================================================

def generate_filename(prefix, filename):

    ext = get_extension(filename)

    unique = uuid.uuid4().hex

    return f"{prefix}_{unique}.{ext}"


# =====================================================
# CREATE UPLOAD FOLDER
# =====================================================

def create_upload_folder(module_name):

    """
    Example:

    uploads/
        va/
            2026/
                07/

    """

    year = datetime.now().strftime("%Y")
    month = datetime.now().strftime("%m")

    folder = os.path.join(

        get_project_root(),

        "uploads",

        module_name,

        year,

        month

    )

    os.makedirs(
        folder,
        exist_ok=True
    )

    return folder


# =====================================================
# BUILD RELATIVE PATH
# =====================================================

def build_relative_path(module_name, filename):

    year = datetime.now().strftime("%Y")
    month = datetime.now().strftime("%m")

    return os.path.join(

        "uploads",

        module_name,

        year,

        month,

        filename

    )


# =====================================================
# BUILD ABSOLUTE PATH
# =====================================================

def build_absolute_path(relative_path):

    return os.path.join(

        get_project_root(),

        relative_path

    )


# =====================================================
# SAVE FILE
# =====================================================

def save_uploaded_file(file, module_name, prefix="FILE"):

    """
    Return:

    {
        file_name,
        original_name,
        relative_path,
        absolute_path,
        extension,
        file_size
    }
    """

    if file is None:

        return None

    if file.filename == "":

        return None

    if not allowed_file(file.filename):

        raise Exception("Unsupported file type.")

    folder = create_upload_folder(module_name)

    filename = generate_filename(

        prefix,

        file.filename

    )

    absolute_path = os.path.join(

        folder,

        filename

    )

    relative_path = build_relative_path(

        module_name,

        filename

    )

    file.save(absolute_path)

    return {

        "file_name": filename,

        "original_name":
            get_original_filename(file),

        "relative_path":
            relative_path,

        "absolute_path":
            absolute_path,

        "extension":
            get_extension(file.filename),

        "file_size":
            os.path.getsize(absolute_path)

    }


# =====================================================
# DELETE FILE
# =====================================================

def delete_file(relative_path):

    if not relative_path:

        return

    absolute_path = build_absolute_path(

        relative_path

    )

    if os.path.exists(absolute_path):

        os.remove(absolute_path)


# =====================================================
# FILE EXISTS
# =====================================================

def file_exists(relative_path):

    absolute_path = build_absolute_path(

        relative_path

    )

    return os.path.exists(absolute_path)


# =====================================================
# GET ABSOLUTE FILE
# =====================================================

def get_absolute_file(relative_path):

    return build_absolute_path(relative_path)