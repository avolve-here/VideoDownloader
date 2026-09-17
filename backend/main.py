

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from yt_dlp import YoutubeDL

import os
import shutil
import tempfile
import threading
import uuid

from starlette.background import BackgroundTask


app = FastAPI(
    title="Nuvexa Video Downloader API",
    version="1.0.0"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# REQUEST MODELS
# ============================================================

class AnalyzeRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: str


class AudioDownloadRequest(BaseModel):
    url: str
    bitrate: int


# ============================================================
# FFMPEG
# ============================================================

LOCAL_FFMPEG = (
    r"C:\Users\aryan\OneDrive\Documents\Prince Files"
    r"\ffmpeg-9.0.1-essentials_build"
    r"\ffmpeg-9.0.1-essentials_build"
    r"\bin"
)

if os.path.exists(LOCAL_FFMPEG):
    FFMPEG_LOCATION = LOCAL_FFMPEG
else:
    FFMPEG_LOCATION = shutil.which("ffmpeg")


# ============================================================
# DOWNLOAD JOB STORAGE
# ============================================================

download_jobs = {}
download_jobs_lock = threading.Lock()


def create_job():

    job_id = str(uuid.uuid4())

    with download_jobs_lock:

        download_jobs[job_id] = {
            "status": "starting",
            "progress": 0,
            "filename": None,
            "filepath": None,
            "error": None,
        }

    return job_id


def update_job(job_id, **values):

    with download_jobs_lock:

        if job_id in download_jobs:

            download_jobs[job_id].update(
                values
            )


def get_job(job_id):

    with download_jobs_lock:

        job = download_jobs.get(
            job_id
        )

        if not job:

            return None

        return dict(job)


# ============================================================
# PROGRESS HOOK
# ============================================================

def create_progress_hook(job_id):

    def progress_hook(data):

        status = data.get("status")

        if status == "downloading":

            downloaded = data.get(
                "downloaded_bytes",
                0
            )

            total = (
                data.get("total_bytes")
                or
                data.get("total_bytes_estimate")
                or
                0
            )

            percentage = 0

            if total:

                percentage = int(
                    (downloaded / total) * 100
                )

                percentage = max(
                    0,
                    min(100, percentage)
                )

            update_job(
                job_id,
                status="downloading",
                progress=percentage
            )

        elif status == "finished":

            update_job(
                job_id,
                status="merging",
                progress=100
            )

    return progress_hook


# ============================================================
# BASIC ROUTES
# ============================================================

@app.get("/")
def home():

    return {
        "status": "online",
        "message": "Nuvexa Video Downloader API is running"
    }


@app.get("/api/health")
def health():

    return {
        "status": "healthy"
    }

# ============================================================
# VIDEO PREVIEW
# ============================================================

@app.get("/api/preview")
def preview_media(url: str):

    url = url.strip()

    if not url:
        raise HTTPException(
            status_code=400,
            detail="URL is required."
        )

    temp_dir = tempfile.mkdtemp()

    output_template = os.path.join(
        temp_dir,
        "preview.%(ext)s"
    )

    ydl_options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,

        # Keep preview relatively small so it loads faster.
        "format": (
            "bestvideo[height<=360]+bestaudio/"
            "best[height<=360]/"
            "best"
        ),

        "outtmpl": output_template,

        "ffmpeg_location": FFMPEG_LOCATION,

        "merge_output_format": "mp4",
    }

    try:

        with YoutubeDL(ydl_options) as ydl:

            ydl.extract_info(
                url,
                download=True
            )

        # Find final MP4 only.
        mp4_files = []

        for file in os.listdir(temp_dir):

            full_path = os.path.join(
                temp_dir,
                file
            )

            if (
                os.path.isfile(full_path)
                and
                file.lower().endswith(".mp4")
            ):

                mp4_files.append(full_path)

        if len(mp4_files) != 1:

            raise Exception(
                "Preview MP4 could not be created."
            )

        filename = mp4_files[0]

        if os.path.getsize(filename) <= 0:

            raise Exception(
                "Preview file is empty."
            )

        def cleanup_preview():

            try:
                shutil.rmtree(
                    temp_dir,
                    ignore_errors=True
                )
            except Exception:
                pass

        return FileResponse(
            filename,
            media_type="video/mp4",
            filename="nuvexa-preview.mp4",
            background=BackgroundTask(
                cleanup_preview
            )
        )

    except Exception as error:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )

        raise HTTPException(
            status_code=400,
            detail=(
                "Unable to create preview: "
                f"{str(error)}"
            )
        )

# ============================================================
# ANALYZE MEDIA
# ============================================================

@app.post("/api/analyze")
def analyze_media(request: AnalyzeRequest):

    url = request.url.strip()

    if not url:

        raise HTTPException(
            status_code=400,
            detail="URL cannot be empty."
        )

    try:

        ydl_options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }

        with YoutubeDL(ydl_options) as ydl:

            info = ydl.extract_info(
                url,
                download=False
            )

        if not info:

            raise Exception(
                "No media information was returned."
            )

        formats = []

        # ====================================================
        # FIND A PLAYABLE PROGRESSIVE PREVIEW
        # ====================================================

        preview_url = None
        preview_format_id = None
        preview_ext = None

        progressive_formats = []

        for media_format in info.get(
            "formats",
            []
        ):

            height = media_format.get(
                "height"
            )

            if height:

                formats.append({
                    "format_id": media_format.get(
                        "format_id"
                    ),

                    "height": height,

                    "ext": media_format.get(
                        "ext"
                    ),

                    "filesize": (
                        media_format.get(
                            "filesize"
                        )
                        or
                        media_format.get(
                            "filesize_approx"
                        )
                    ),

                    "has_audio": (
                        media_format.get(
                            "acodec"
                        )
                        not in (
                            None,
                            "none"
                        )
                    ),

                    "has_video": (
                        media_format.get(
                            "vcodec"
                        )
                        not in (
                            None,
                            "none"
                        )
                    ),
                })

            # A progressive format has both
            # video and audio in one URL.
            if (
                media_format.get("url")
                and
                media_format.get("vcodec")
                not in (None, "none")
                and
                media_format.get("acodec")
                not in (None, "none")
            ):

                progressive_formats.append(
                    media_format
                )

        # ====================================================
        # PICK THE BEST REASONABLE PREVIEW
        # ====================================================

        if progressive_formats:

            progressive_formats.sort(
                key=lambda item: (
                    item.get("height") or 0
                ),
                reverse=True
            )

            selected_preview = (
                progressive_formats[0]
            )

            preview_url = (
                selected_preview.get("url")
            )

            preview_format_id = (
                selected_preview.get(
                    "format_id"
                )
            )

            preview_ext = (
                selected_preview.get("ext")
            )

        # ====================================================
        # RESPONSE
        # ====================================================

        return {

            "status": "success",

            "title": (
                info.get("title")
                or "Unknown media"
            ),

            "thumbnail": info.get(
                "thumbnail"
            ),

            "duration": info.get(
                "duration"
            ),

            "uploader": info.get(
                "uploader"
            ),

            "preview_url": preview_url,

            "preview_format_id": (
                preview_format_id
            ),

            "preview_ext": preview_ext,

            "formats": formats,
        }

    except Exception as error:

        raise HTTPException(
            status_code=400,
            detail=(
                "Unable to analyze this URL: "
                f"{str(error)}"
            )
        )


# ============================================================
# START VIDEO DOWNLOAD
# ============================================================

@app.post("/api/download")
def start_download(
    request: DownloadRequest
):

    url = request.url.strip()
    format_id = request.format_id.strip()

    if not url or not format_id:

        raise HTTPException(
            status_code=400,
            detail="URL and format are required."
        )

    job_id = create_job()

    thread = threading.Thread(
        target=process_video_download,
        args=(
            job_id,
            url,
            format_id,
        ),
        daemon=True
    )

    thread.start()

    return {
        "status": "started",
        "job_id": job_id,
    }


# ============================================================
# VIDEO DOWNLOAD WORKER
# ============================================================

def process_video_download(
    job_id,
    url,
    format_id
):

    temp_dir = tempfile.mkdtemp()

    output_template = os.path.join(
        temp_dir,
        "%(title)s.%(ext)s"
    )

    progress_hook = create_progress_hook(
        job_id
    )

    ydl_options = {

        "quiet": True,

        "no_warnings": True,

        "noplaylist": True,

        "format": (
            f"{format_id}+bestaudio/"
            f"{format_id}"
        ),

        "outtmpl": output_template,

        "ffmpeg_location": FFMPEG_LOCATION,

        "merge_output_format": "mp4",

        "progress_hooks": [
            progress_hook
        ],
    }

    try:

        update_job(
            job_id,
            status="preparing",
            progress=0
        )

        with YoutubeDL(
            ydl_options
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            prepared_filename = (
                ydl.prepare_filename(
                    info
                )
            )

        # ====================================================
        # FIND FINAL MP4
        # ====================================================

        prepared_base = os.path.splitext(
            prepared_filename
        )[0]

        expected_filename = (
            prepared_base
            + ".mp4"
        )

        if os.path.isfile(
            expected_filename
        ):

            filename = expected_filename

        else:

            mp4_files = []

            for file in os.listdir(
                temp_dir
            ):

                full_path = os.path.join(
                    temp_dir,
                    file
                )

                if (
                    os.path.isfile(full_path)
                    and
                    file.lower().endswith(".mp4")
                ):

                    mp4_files.append(
                        full_path
                    )

            if len(mp4_files) == 1:

                filename = mp4_files[0]

            elif len(mp4_files) > 1:

                matching_files = [
                    file
                    for file in mp4_files
                    if os.path.splitext(
                        os.path.basename(file)
                    )[0]
                    ==
                    os.path.splitext(
                        os.path.basename(
                            prepared_filename
                        )
                    )[0]
                ]

                if len(matching_files) == 1:

                    filename = (
                        matching_files[0]
                    )

                else:

                    raise Exception(
                        "Multiple MP4 files were "
                        "created and the final file "
                        "could not be identified safely."
                    )

            else:

                raise Exception(
                    "Final MP4 file was not created."
                )

        # ====================================================
        # SAFETY CHECK
        # ====================================================

        if not os.path.isfile(
            filename
        ):

            raise Exception(
                "Final downloaded file does not exist."
            )

        file_size = os.path.getsize(
            filename
        )

        if file_size <= 0:

            raise Exception(
                "Final downloaded file is empty."
            )

        # ====================================================
        # COMPLETE
        # ====================================================

        update_job(
            job_id,

            status="completed",

            progress=100,

            filename=os.path.basename(
                filename
            ),

            filepath=filename
        )

    except Exception as error:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )

        update_job(
            job_id,

            status="error",

            progress=0,

            error=str(error)
        )


# ============================================================
# DOWNLOAD STATUS
# ============================================================

@app.get(
    "/api/download-status/{job_id}"
)
def download_status(
    job_id: str
):

    job = get_job(
        job_id
    )

    if not job:

        raise HTTPException(
            status_code=404,
            detail="Download job not found."
        )

    return {

        "status": job["status"],

        "progress": job["progress"],

        "filename": job["filename"],

        "error": job["error"],
    }


# ============================================================
# GET COMPLETED VIDEO
# ============================================================

@app.get(
    "/api/download-file/{job_id}"
)
def download_file(
    job_id: str
):

    job = get_job(
        job_id
    )

    if not job:

        raise HTTPException(
            status_code=404,
            detail="Download job not found."
        )

    if job["status"] != "completed":

        raise HTTPException(
            status_code=400,
            detail="Download is not ready yet."
        )

    filepath = job["filepath"]

    if (
        not filepath
        or
        not os.path.isfile(filepath)
    ):

        raise HTTPException(
            status_code=404,
            detail="Downloaded file no longer exists."
        )

    temp_dir = os.path.dirname(
        filepath
    )

    def cleanup():

        try:

            shutil.rmtree(
                temp_dir,
                ignore_errors=True
            )

        except Exception:
            pass

        with download_jobs_lock:

            download_jobs.pop(
                job_id,
                None
            )

    return FileResponse(

        filepath,

        media_type="video/mp4",

        filename=job["filename"],

        background=BackgroundTask(
            cleanup
        )
    )


# ============================================================
# AUDIO DOWNLOAD
# ============================================================

@app.post(
    "/api/download-audio"
)
def download_audio(
    request: AudioDownloadRequest
):

    url = request.url.strip()
    bitrate = request.bitrate

    if not url:

        raise HTTPException(
            status_code=400,
            detail="URL is required."
        )

    allowed_bitrates = {
        128,
        192,
        320
    }

    if bitrate not in allowed_bitrates:

        raise HTTPException(
            status_code=400,
            detail="Unsupported audio bitrate."
        )

    temp_dir = tempfile.mkdtemp()

    output_template = os.path.join(
        temp_dir,
        "%(title)s.%(ext)s"
    )

    ydl_options = {

        "quiet": True,

        "no_warnings": True,

        "noplaylist": True,

        "format": "bestaudio/best",

        "outtmpl": output_template,

        "ffmpeg_location": FFMPEG_LOCATION,

        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",

                "preferredcodec": "mp3",

                "preferredquality": str(
                    bitrate
                ),
            }
        ],
    }

    try:

        with YoutubeDL(
            ydl_options
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            original_filename = (
                ydl.prepare_filename(
                    info
                )
            )

        filename = (
            os.path.splitext(
                original_filename
            )[0]
            + ".mp3"
        )

        if not os.path.isfile(
            filename
        ):

            mp3_files = []

            for file in os.listdir(
                temp_dir
            ):

                full_path = os.path.join(
                    temp_dir,
                    file
                )

                if (
                    os.path.isfile(full_path)
                    and
                    file.lower().endswith(".mp3")
                ):

                    mp3_files.append(
                        full_path
                    )

            if len(mp3_files) == 1:

                filename = mp3_files[0]

            elif len(mp3_files) > 1:

                raise Exception(
                    "Multiple MP3 files were created "
                    "and the final file could not be "
                    "identified safely."
                )

            else:

                raise Exception(
                    "MP3 file was not created."
                )

        if not os.path.isfile(
            filename
        ):

            raise Exception(
                "Final MP3 file does not exist."
            )

        if os.path.getsize(
            filename
        ) <= 0:

            raise Exception(
                "Final MP3 file is empty."
            )

        def cleanup_audio():

            try:

                shutil.rmtree(
                    temp_dir,
                    ignore_errors=True
                )

            except Exception:
                pass

        return FileResponse(

            filename,

            media_type="audio/mpeg",

            filename=os.path.basename(
                filename
            ),

            background=BackgroundTask(
                cleanup_audio
            )
        )

    except Exception as error:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )

        raise HTTPException(
            status_code=400,
            detail=(
                "Audio download failed: "
                f"{str(error)}"
            )
        )


# ============================================================
# DOWNLOAD STATUS
# ============================================================

@app.get(
    "/api/download-status/{job_id}"
)
def download_status(
    job_id: str
):

    job = get_job(
        job_id
    )

    if not job:

        raise HTTPException(
            status_code=404,
            detail="Download job not found."
        )

    return {

        "status": job["status"],

        "progress": job["progress"],

        "filename": job["filename"],

        "error": job["error"],
    }


# ============================================================
# GET COMPLETED VIDEO
# ============================================================

@app.get(
    "/api/download-file/{job_id}"
)
def download_file(
    job_id: str
):

    job = get_job(
        job_id
    )

    if not job:

        raise HTTPException(
            status_code=404,
            detail="Download job not found."
        )

    if job["status"] != "completed":

        raise HTTPException(
            status_code=400,
            detail="Download is not ready yet."
        )

    filepath = job["filepath"]

    if (
        not filepath
        or
        not os.path.isfile(filepath)
    ):

        raise HTTPException(
            status_code=404,
            detail="Downloaded file no longer exists."
        )

    temp_dir = os.path.dirname(
        filepath
    )

    def cleanup():

        try:

            shutil.rmtree(
                temp_dir,
                ignore_errors=True
            )

        except Exception:
            pass

        with download_jobs_lock:

            download_jobs.pop(
                job_id,
                None
            )

    return FileResponse(

        filepath,

        media_type="video/mp4",

        filename=job["filename"],

        background=BackgroundTask(
            cleanup
        )
    )


# ============================================================
# AUDIO DOWNLOAD
# ============================================================

@app.post(
    "/api/download-audio"
)
def download_audio(
    request: AudioDownloadRequest
):

    url = request.url.strip()
    bitrate = request.bitrate

    if not url:

        raise HTTPException(
            status_code=400,
            detail="URL is required."
        )

    allowed_bitrates = {
        128,
        192,
        320
    }

    if bitrate not in allowed_bitrates:

        raise HTTPException(
            status_code=400,
            detail="Unsupported audio bitrate."
        )

    temp_dir = tempfile.mkdtemp()

    output_template = os.path.join(
        temp_dir,
        "%(title)s.%(ext)s"
    )

    ydl_options = {

        "quiet": True,

        "no_warnings": True,

        "noplaylist": True,

        "format": "bestaudio/best",

        "outtmpl": output_template,

        "ffmpeg_location": FFMPEG_LOCATION,

        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",

                "preferredcodec": "mp3",

                "preferredquality": str(
                    bitrate
                ),
            }
        ],
    }

    try:

        with YoutubeDL(
            ydl_options
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            original_filename = (
                ydl.prepare_filename(
                    info
                )
            )

        filename = (
            os.path.splitext(
                original_filename
            )[0]
            + ".mp3"
        )

        if not os.path.isfile(
            filename
        ):

            mp3_files = []

            for file in os.listdir(
                temp_dir
            ):

                full_path = os.path.join(
                    temp_dir,
                    file
                )

                if (
                    os.path.isfile(full_path)
                    and
                    file.lower().endswith(".mp3")
                ):

                    mp3_files.append(
                        full_path
                    )

            if len(mp3_files) == 1:

                filename = mp3_files[0]

            elif len(mp3_files) > 1:

                raise Exception(
                    "Multiple MP3 files were created "
                    "and the final file could not be "
                    "identified safely."
                )

            else:

                raise Exception(
                    "MP3 file was not created."
                )

        if not os.path.isfile(
            filename
        ):

            raise Exception(
                "Final MP3 file does not exist."
            )

        if os.path.getsize(
            filename
        ) <= 0:

            raise Exception(
                "Final MP3 file is empty."
            )

        def cleanup_audio():

            try:

                shutil.rmtree(
                    temp_dir,
                    ignore_errors=True
                )

            except Exception:
                pass

        return FileResponse(

            filename,

            media_type="audio/mpeg",

            filename=os.path.basename(
                filename
            ),

            background=BackgroundTask(
                cleanup_audio
            )
        )

    except Exception as error:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )

        raise HTTPException(
            status_code=400,
            detail=(
                "Audio download failed: "
                f"{str(error)}"
            )
        )