# Deployment packaging policy

- Never include historical images, camera captures, diagnostic images, point clouds, temporary uploads, or SDK sample captures in any deployment package.
- Never copy the entire `media` directory or `2d_SDK` directory. Use the packaging resource allowlist; retain only necessary standard templates and camera parameter files. Calibration and recipe data in the database must be preserved.
- Deliver uncompressed deployment directories unless the user explicitly requests an archive.
- Both AGV and external computers need the complete application. AGV routes MES requests over HTTP to the external computer; only the external computer accesses company MES. AGV starts PLC listening automatically; external computer retains hardware functions but does not automatically control AGV hardware.
