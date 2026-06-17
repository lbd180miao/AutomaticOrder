# Hik Camera Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal Django device adapter for capturing images through the `chg_hik` Hik camera binding.

**Architecture:** Keep vendor SDK calls isolated in `apps.devices.adapters.camera.CameraAdapter`. Read configuration from `settings.AUTOMATIC_ORDER["HIK_CAMERA"]`, lazily import `chg_hik`, and return a small dict for downstream services.

**Tech Stack:** Django 6, Python standard library, `chg_hik` vendor extension.

---

### Task 1: Add CameraAdapter Tests

**Files:**
- Modify: `apps/devices/tests.py`

- [ ] **Step 1: Write failing tests**

Add tests that inject fake `chg_hik` modules and assert IP-direct mode, enumeration mode, and missing module errors.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.devices.tests -v 2`

Expected: failures because `CameraAdapter.capture()` currently raises `NotImplementedError`.

### Task 2: Implement CameraAdapter

**Files:**
- Modify: `apps/devices/adapters/camera.py`
- Modify: `AutomaticOrder/settings.py`

- [ ] **Step 1: Implement settings defaults**

Add `AUTOMATIC_ORDER["HIK_CAMERA"]` with `OUTPUT_DIR`, `CAMERA_IP`, `PC_IP`, `FORMAT`, and `QUALITY`.

- [ ] **Step 2: Implement capture behavior**

Create the output directory, lazily import `chg_hik`, instantiate `chg_hik.Camera`, call `open()` with configured IP values when both are present, call `capture()`, and return the adapter result dict.

- [ ] **Step 3: Run focused tests**

Run: `python manage.py test apps.devices.tests -v 2`

Expected: all adapter tests pass.

### Task 3: Verify Project

**Files:**
- No code changes

- [ ] **Step 1: Run broader Django checks**

Run: `python manage.py test apps.devices apps.core -v 2`

Expected: all selected tests pass.
