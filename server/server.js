import "dotenv/config";
import express from "express";
import cors from "cors";

import routes from "./Routes/imageRoutes.js";

/**
 * Express API server entrypoint.
 *
 * Responsibilities:
 * - Connect to MongoDB.
 * - Configure CORS + JSON/body parsers sized for image payload metadata.
 * - Mount API routes implemented in `routes/imageRoutes.js`.
 */

const app = express();

app.use(
	cors({
		origin: true,
		methods: ["GET", "POST", "OPTIONS"],
	}),
);

// Body parsing for JSON + URL-encoded payloads (image data is stored as base64 strings).
app.use(express.json({ limit: "50mb" }));
app.use(express.urlencoded({ limit: "50mb", extended: true }));

app.use(routes);

app.listen(process.env.PORT || 8001, () => {
	console.log("Server running on port 8001");
});
