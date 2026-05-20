import express from "express";
import multer from "multer";
import axios from "axios";
import fs from "fs";
import FormData from "form-data";
const router = express.Router();
const upload = multer({ dest: "uploads/" });

router.get("/health", async (req, res) => {
	try {
		const response = await axios.get("http://localhost:8000/health");
		res.json(response.data);
	} catch (err) {
		res.status(502).json({ error: "Background removal python service is unreachable" });
	}
});

router.post(["/remove-bg", "/remove-background", "/remove-bg-variants", "/remove-background-variants"], upload.single("file"), async (req, res) => {
	try {
		if (!req.file) {
			return res.status(400).send("Missing image file");
		}

		const imagePath = req.file.path;

		const form = new FormData();

		form.append("file", fs.createReadStream(imagePath), {
			filename: req.file.originalname || "image",
			contentType: req.file.mimetype,
		});
		// Frontend should only control how many images to generate.
		// Everything else is enforced here to keep the client simple.
		const variantsMode = req.path.includes("variants");
		const defaultVariations = variantsMode ? "4" : "1";
		const rawNumVariations = req.body?.num_variations ?? req.body?.numVariations ?? req.query?.num_variations ?? defaultVariations;
		const parsedNumVariations = Math.max(1, Number.parseInt(String(rawNumVariations), 10) || 1);
		const effectiveVariations = variantsMode ? Math.max(2, parsedNumVariations) : parsedNumVariations;
		const multiBorderEnabled = variantsMode ? true : effectiveVariations > 1;
		console.log(`[remove-bg] ${req.method} ${req.originalUrl} num_variations=${effectiveVariations} multi_border=${multiBorderEnabled}`);

		// Keep Express dumb: Python service owns the behavior.
		// Forward all body parameters (excluding file) and query parameters to the Python service.
		if (req.body) {
			for (const [key, value] of Object.entries(req.body)) {
				if (key !== "file" && value !== undefined && value !== null) {
					form.append(key, String(value));
				}
			}
		}
		if (req.query) {
			for (const [key, value] of Object.entries(req.query)) {
				if (key !== "file" && value !== undefined && value !== null) {
					form.append(key, String(value));
				}
			}
		}

		if (multiBorderEnabled) {
			form.append("num_variations", String(effectiveVariations));
			form.append("multi_border", "true");
		}

		const response = await axios.post("http://localhost:8000/remove-bg", form, {
			headers: form.getHeaders(),
			responseType: "arraybuffer",
		});

		const contentType = response.headers["content-type"] || "application/octet-stream";

		if (contentType.includes("application/json")) {
			// response.data is an ArrayBuffer; convert to string then parse JSON
			const text = Buffer.from(response.data).toString("utf8");
			let parsed = {};
			try {
				parsed = JSON.parse(text);
			} catch (err) {
				console.error("Failed to parse JSON from python service", err);
				return res.status(502).json({ error: "Invalid JSON from upstream service" });
			}
			res.json(parsed);
		} else {
			res.set("Content-Type", contentType);
			res.send(Buffer.from(response.data));
		}
	} catch (err) {
		console.error(err);
		res.status(500).send("Error processing image");
	} finally {
		// Always delete the temporary upload to avoid leaking disk space.
		if (req.file?.path) {
			fs.promises.unlink(req.file.path).catch(() => {});
		}
	}
});

export default router;
