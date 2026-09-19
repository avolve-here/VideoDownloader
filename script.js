const analyzeBtn = document.getElementById("analyzeBtn");
const urlInput = document.getElementById("urlInput");
const pasteBtn = document.getElementById("pasteBtn");

const API_BASE = "https://nuvexa-videodownloader.onrender.com";

pasteBtn.addEventListener("click", async () => {
    try {
        const text = await navigator.clipboard.readText();

        if (text) {
            urlInput.value = text;
            urlInput.focus();

            pasteBtn.textContent = "Pasted ✓";

            setTimeout(() => {
                pasteBtn.textContent = "Paste";
            }, 1500);
        } else {
            pasteBtn.textContent = "Nothing to paste";

            setTimeout(() => {
                pasteBtn.textContent = "Paste";
            }, 1500);
        }

    } catch (error) {
        pasteBtn.textContent = "Use Ctrl+V";

        setTimeout(() => {
            pasteBtn.textContent = "Paste";
        }, 1500);
    }
});

const searchPanel = document.getElementById("downloader");
const resultsSection = document.getElementById("results");
const closeResults = document.getElementById("closeResults");

const mediaTitle = document.getElementById("mediaTitle");
const mediaDetails = document.getElementById("mediaDetails");

const mediaPlayer = document.getElementById("mediaPlayer");
const playerPlaceholder = document.getElementById("playerPlaceholder");

let currentFormats = [];
let previewObjectUrl = null;


// ============================================================
// INITIAL STATE
// ============================================================

resultsSection.style.display = "none";
searchPanel.style.display = "flex";


// ============================================================
// ANALYZE EVENTS
// ============================================================

analyzeBtn.addEventListener("click", analyzeMedia);

urlInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        analyzeMedia();
    }
});


// ============================================================
// ANALYZE MEDIA
// ============================================================

async function analyzeMedia() {

    const url = urlInput.value.trim();

    if (!url) {
        showError("Please paste a video or media URL.");
        return;
    }

    try {
        const parsedUrl = new URL(url);

        if (!["http:", "https:"].includes(parsedUrl.protocol)) {
            throw new Error();
        }

    } catch {
        showError("Please enter a valid URL.");
        return;
    }

    analyzeBtn.disabled = true;
    analyzeBtn.textContent = "Analyzing...";

    mediaTitle.textContent = "Analyzing media...";
    mediaDetails.textContent =
        "Nuvexa is retrieving media information.";

    resetPlayer();

    try {

        const response = await fetch(
            `${API_BASE}/api/analyze`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    url: url
                })
            }
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.detail || "Analysis failed."
            );
        }

        currentFormats = data.formats || [];

        mediaTitle.textContent =
            data.title || "Media detected";

        const details = [];

        if (data.uploader) {
            details.push(`By ${data.uploader}`);
        }

        if (data.duration) {
            details.push(
                `Duration: ${formatDuration(data.duration)}`
            );
        }

        details.push(
            `${currentFormats.length} formats detected`
        );

        mediaDetails.textContent =
            details.join(" • ");

        loadPreview(
            data.preview_url,
            data.thumbnail
        );

        renderVideoOptions(currentFormats);
        renderAudioOptions();

        searchPanel.style.display = "none";
        resultsSection.style.display = "block";

        resultsSection.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });

    } catch (error) {

        console.error(
            "Nuvexa analyze error:",
            error
        );

        showError(
            error.message ||
            "Unable to connect to the Nuvexa server."
        );

    } finally {

        analyzeBtn.disabled = false;
        analyzeBtn.textContent = "Analyze";
    }
}


// ============================================================
// LOAD PLAYABLE PREVIEW
// ============================================================

async function loadPreview(previewUrl, thumbnail) {

    if (!mediaPlayer) {
        return;
    }

    mediaPlayer.pause();

    mediaPlayer.removeAttribute("src");
    mediaPlayer.removeAttribute("poster");

    mediaPlayer.load();

    if (previewObjectUrl) {
        URL.revokeObjectURL(previewObjectUrl);
        previewObjectUrl = null;
    }

    if (thumbnail) {
        mediaPlayer.poster = thumbnail;
    }

    if (playerPlaceholder) {
        playerPlaceholder.style.display = "flex";
        playerPlaceholder.style.backgroundImage = "";
    }

    try {

        const sourceUrl =
            `${API_BASE}/api/preview?url=${encodeURIComponent(
                urlInput.value.trim()
            )}`;

        const response = await fetch(sourceUrl);

        if (!response.ok) {

            let message =
                "Preview could not be loaded.";

            try {
                const data = await response.json();
                message = data.detail || message;
            } catch {}

            throw new Error(message);
        }

        const blob = await response.blob();

        previewObjectUrl = URL.createObjectURL(blob);

        mediaPlayer.src = previewObjectUrl;
        mediaPlayer.load();

        if (playerPlaceholder) {
            playerPlaceholder.style.display = "none";
        }

    } catch (error) {

        console.error(
            "Nuvexa preview error:",
            error
        );

        showPlayerPlaceholder(thumbnail);
    }
}


// ============================================================
// PLAYER PLACEHOLDER
// ============================================================

function showPlayerPlaceholder(thumbnail) {

    if (!playerPlaceholder) {
        return;
    }

    playerPlaceholder.style.display = "flex";

    if (thumbnail) {

        playerPlaceholder.style.backgroundImage =
            `linear-gradient(
                rgba(16, 38, 45, 0.78),
                rgba(16, 38, 45, 0.78)
            ), url("${thumbnail}")`;

        playerPlaceholder.style.backgroundSize = "cover";
        playerPlaceholder.style.backgroundPosition = "center";

    } else {

        playerPlaceholder.style.backgroundImage = "";
    }
}


// ============================================================
// VIDEO OPTIONS
// ============================================================

function renderVideoOptions(formats) {

    const groups =
        document.querySelectorAll(".download-group");

    if (groups.length === 0) {
        return;
    }

    const videoContainer =
        groups[0].querySelector(".download-options");

    if (!videoContainer) {
        return;
    }

    videoContainer.innerHTML = "";

    const uniqueFormats = [];
    const seenHeights = new Set();

    formats
        .filter(format => format.height)
        .sort((a, b) => b.height - a.height)
        .forEach(format => {

            if (!seenHeights.has(format.height)) {

                seenHeights.add(format.height);
                uniqueFormats.push(format);
            }
        });

    if (uniqueFormats.length === 0) {

        videoContainer.innerHTML =
            "<p>No video formats detected.</p>";

        return;
    }

    const visibleFormats =
        uniqueFormats.filter(
            format => format.height >= 360
        );

    const hiddenFormats =
        uniqueFormats.filter(
            format => format.height < 360
        );

    visibleFormats.forEach(format => {

        const button =
            createVideoButton(format);

        videoContainer.appendChild(button);
    });

    if (hiddenFormats.length > 0) {

        const moreButton =
            document.createElement("button");

        moreButton.type = "button";
        moreButton.className =
            "more-quality-button";

        moreButton.textContent = "More ▾";

        const hiddenContainer =
            document.createElement("div");

        hiddenContainer.className =
            "more-quality-options";

        hiddenContainer.style.display = "none";

        hiddenFormats.forEach(format => {

            const button =
                createVideoButton(format);

            hiddenContainer.appendChild(button);
        });

        moreButton.addEventListener("click", () => {

            const isHidden =
                hiddenContainer.style.display === "none";

            if (isHidden) {

                hiddenContainer.style.display = "flex";
                moreButton.textContent = "Less ▴";

            } else {

                hiddenContainer.style.display = "none";
                moreButton.textContent = "More ▾";
            }
        });

        videoContainer.appendChild(moreButton);
        videoContainer.appendChild(hiddenContainer);
    }
}


// ============================================================
// CREATE VIDEO BUTTON
// ============================================================

function createVideoButton(format) {

    const button =
        document.createElement("button");

    button.type = "button";
    button.className = "download-option";

    const formatName =
        format.ext
            ? format.ext.toUpperCase()
            : "VIDEO";

    button.innerHTML = `
        <div>
            <strong>${format.height}p</strong>
            <small>${formatName}</small>
        </div>

        <span>Download</span>
    `;

    button.addEventListener("click", () => {
        downloadFormat(format, button);
    });

    return button;
}


// ============================================================
// AUDIO OPTIONS
// ============================================================

function renderAudioOptions() {

    const groups =
        document.querySelectorAll(".download-group");

    if (groups.length < 2) {
        return;
    }

    const audioContainer =
        groups[1].querySelector(".download-options");

    if (!audioContainer) {
        return;
    }

    audioContainer.innerHTML = "";

    const audioQualities = [
        {
            bitrate: 128,
            format: "MP3"
        },
        {
            bitrate: 192,
            format: "MP3"
        },
        {
            bitrate: 320,
            format: "MP3"
        }
    ];

    audioQualities.forEach(option => {

        const button =
            document.createElement("button");

        button.type = "button";
        button.className = "download-option";

        button.innerHTML = `
            <div>
                <strong>
                    ${option.bitrate} kbps
                </strong>

                <small>
                    ${option.format}
                </small>
            </div>

            <span>
                Download
            </span>
        `;

        button.addEventListener("click", () => {

            downloadAudio(
                option.bitrate,
                button
            );
        });

        audioContainer.appendChild(button);
    });
}


// ============================================================
// VIDEO DOWNLOAD
// ============================================================

async function downloadFormat(format, clickedButton) {

    const url = urlInput.value.trim();

    if (!url) {

        alert(
            "Please analyze the URL again."
        );

        return;
    }

    clickedButton.disabled = true;

    const statusText =
        clickedButton.querySelector("span");

    statusText.textContent = "Preparing...";

    try {

        const response = await fetch(
            `${API_BASE}/api/download`,
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    url: url,
                    format_id: format.format_id
                })
            }
        );

        const data = await response.json();

        if (!response.ok) {

            throw new Error(
                data.detail ||
                "Download failed."
            );
        }

        if (!data.job_id) {

            throw new Error(
                "Server did not create a download job."
            );
        }

        await monitorDownload(
            data.job_id,
            clickedButton
        );

    } catch (error) {

        console.error(
            "Nuvexa download error:",
            error
        );

        statusText.textContent = "Download";
        clickedButton.disabled = false;

        alert(
            error.message ||
            "Unable to download this format."
        );
    }
}


// ============================================================
// MONITOR DOWNLOAD
// ============================================================

async function monitorDownload(
    jobId,
    clickedButton
) {

    const statusText =
        clickedButton.querySelector("span");

    while (true) {

        await sleep(700);

        const response = await fetch(
            `${API_BASE}/api/download-status/${jobId}`
        );

        const data = await response.json();

        if (!response.ok) {

            throw new Error(
                data.detail ||
                "Unable to check download status."
            );
        }

        if (
            data.status === "starting" ||
            data.status === "preparing"
        ) {

            statusText.textContent =
                "Preparing...";

        } else if (
            data.status === "downloading"
        ) {

            statusText.textContent =
                `Downloading ${data.progress}%`;

        } else if (
            data.status === "merging"
        ) {

            statusText.textContent =
                "Merging...";

        } else if (
            data.status === "completed"
        ) {

            statusText.textContent =
                "Done ✓";

            await fetchCompletedFile(jobId);

            await sleep(1500);

            statusText.textContent =
                "Download";

            clickedButton.disabled = false;

            return;

        } else if (
            data.status === "error"
        ) {

            throw new Error(
                data.error ||
                "Download failed."
            );
        }
    }
}


// ============================================================
// FETCH FINAL COMPLETED FILE
// ============================================================

async function fetchCompletedFile(jobId) {

    const response = await fetch(
        `${API_BASE}/api/download-file/${jobId}`
    );

    if (!response.ok) {

        let errorMessage =
            "Unable to retrieve the completed file.";

        try {

            const errorData =
                await response.json();

            errorMessage =
                errorData.detail ||
                errorMessage;

        } catch {}

        throw new Error(errorMessage);
    }

    const blob =
        await response.blob();

    const filename =
        getFilenameFromResponse(response);

    saveBlob(
        blob,
        filename ||
        `${safeFilename(mediaTitle.textContent)}.mp4`
    );
}


// ============================================================
// GET SERVER FILENAME
// ============================================================

function getFilenameFromResponse(response) {

    const disposition =
        response.headers.get(
            "Content-Disposition"
        );

    if (!disposition) {
        return null;
    }

    const match =
        disposition.match(
            /filename="?([^"]+)"?/i
        );

    return match
        ? match[1]
        : null;
}


// ============================================================
// AUDIO DOWNLOAD
// ============================================================

async function downloadAudio(
    bitrate,
    clickedButton
) {

    const url = urlInput.value.trim();

    if (!url) {

        alert(
            "Please analyze the URL again."
        );

        return;
    }

    clickedButton.disabled = true;

    const statusText =
        clickedButton.querySelector("span");

    const originalText =
        statusText.textContent;

    statusText.textContent =
        "Preparing...";

    try {

        const response = await fetch(
            `${API_BASE}/api/download-audio`,
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify({
                    url: url,
                    bitrate: bitrate
                })
            }
        );

        if (!response.ok) {

            let errorMessage =
                "Audio download failed.";

            try {

                const errorData =
                    await response.json();

                errorMessage =
                    errorData.detail ||
                    errorMessage;

            } catch {}

            throw new Error(errorMessage);
        }

        const blob =
            await response.blob();

        saveBlob(
            blob,
            `${safeFilename(
                mediaTitle.textContent
            )}.mp3`
        );

    } catch (error) {

        alert(
            error.message ||
            "Unable to download audio."
        );

    } finally {

        clickedButton.disabled = false;
        statusText.textContent = originalText;
    }
}


// ============================================================
// CLOSE RESULTS
// ============================================================

closeResults.addEventListener("click", () => {

    resetPlayer();

    document
        .querySelectorAll(".download-options")
        .forEach(container => {
            container.innerHTML = "";
        });

    mediaTitle.textContent =
        "Media title";

    mediaDetails.textContent =
        "Media details";

    urlInput.value = "";

    resultsSection.style.display =
        "none";

    searchPanel.style.display =
        "flex";

    searchPanel.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });
});


// ============================================================
// RESET PLAYER
// ============================================================

function resetPlayer() {

    if (!mediaPlayer) {
        return;
    }

    mediaPlayer.pause();

    mediaPlayer.removeAttribute("src");
    mediaPlayer.removeAttribute("poster");

    mediaPlayer.load();

    if (previewObjectUrl) {

        URL.revokeObjectURL(
            previewObjectUrl
        );

        previewObjectUrl = null;
    }

    if (playerPlaceholder) {

        playerPlaceholder.style.display =
            "flex";

        playerPlaceholder.style.backgroundImage =
            "";
    }
}


// ============================================================
// SAVE FILE
// ============================================================

function saveBlob(blob, filename) {

    const downloadUrl =
        window.URL.createObjectURL(blob);

    const link =
        document.createElement("a");

    link.href = downloadUrl;
    link.download = filename;

    document.body.appendChild(link);

    link.click();

    link.remove();

    setTimeout(() => {

        window.URL.revokeObjectURL(
            downloadUrl
        );

    }, 1000);
}


// ============================================================
// SAFE FILENAME
// ============================================================

function safeFilename(name) {

    return (
        name ||
        "nuvexa-download"
    )
        .replace(
            /[<>:"/\\|?*]/g,
            ""
        )
        .trim()
        .substring(0, 150);
}


// ============================================================
// FORMAT DURATION
// ============================================================

function formatDuration(seconds) {

    const totalSeconds =
        Number(seconds);

    if (
        !Number.isFinite(
            totalSeconds
        )
    ) {
        return "Unknown";
    }

    const hours =
        Math.floor(
            totalSeconds / 3600
        );

    const minutes =
        Math.floor(
            (totalSeconds % 3600) / 60
        );

    const secs =
        Math.floor(
            totalSeconds % 60
        );

    if (hours > 0) {

        return (
            `${hours}:` +
            `${String(minutes).padStart(2, "0")}:` +
            `${String(secs).padStart(2, "0")}`
        );
    }

    return (
        `${minutes}:` +
        `${String(secs).padStart(2, "0")}`
    );
}


// ============================================================
// SLEEP
// ============================================================

function sleep(milliseconds) {

    return new Promise(resolve =>
        setTimeout(resolve, milliseconds)
    );
}


// ============================================================
// ERROR
// ============================================================

function showError(message) {

    console.error(
        "Nuvexa error:",
        message
    );

    alert(message);

    searchPanel.style.display = "flex";
    resultsSection.style.display = "none";

    analyzeBtn.disabled = false;
    analyzeBtn.textContent = "Analyze";

    urlInput.focus();
}