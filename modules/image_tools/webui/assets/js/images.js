/*
 * Image Tools - WebUI Gallery & Viewer Controller
 * Interacts with /api/ext/image_tools/ routes.
 */

const IMAGE_TOOLS_STORE = {
    images: [],
    loading: false,
    error: "",
    activeImage: null,

    async loadImages() {
        this.loading = true;
        this.error = "";
        try {
            const data = await simpleApiFetch("/api/ext/image_tools/list");
            this.images = (data && data.images) ? data.images : [];
        } catch (e) {
            this.error = (typeof e === "string") ? e : "Failed to load image gallery";
        } finally {
            this.loading = false;
        }
    },

    openViewer(imageObj) {
        this.activeImage = imageObj;
        if (Alpine.store("ui")) {
            Alpine.store("ui").openModal("image_viewer");
        }
    },

    closeModal() {
        this.activeImage = null;
        if (Alpine.store("ui")) {
            Alpine.store("ui").closeModal();
        }
    },

    async deleteActive() {
        if (!this.activeImage) return;
        const fname = this.activeImage.filename;
        if (!confirm(`Are you sure you want to delete ${fname}?`)) return;

        try {
            await simpleApiPost("/api/ext/image_tools/delete", { filename: fname });
            this.closeModal();
            await this.loadImages();
        } catch (e) {
            alert(typeof e === "string" ? e : "Failed to delete image");
        }
    }
};

function imageToolsComponent() {
    return {
        get images() {
            return Alpine.store("imageTools").images;
        },
        get loading() {
            return Alpine.store("imageTools").loading;
        },
        get error() {
            return Alpine.store("imageTools").error;
        },
        refresh(force = false) {
            Alpine.store("imageTools").loadImages();
        },
        openImage(img) {
            Alpine.store("imageTools").openViewer(img);
        }
    };
}

document.addEventListener("alpine:init", () => {
    Alpine.store("imageTools", IMAGE_TOOLS_STORE);
});
