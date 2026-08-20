from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, call, patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from zapzap.features.tray.sys_tray_manager import SysTrayManager


WINDOWS_WORKFLOW = (
    REPOSITORY_ROOT / ".github" / "workflows" / "build-windows.yml"
)
WINDOWS_BUILD_SCRIPT = (
    REPOSITORY_ROOT / ".github" / "packaging" / "windows" / "build.ps1"
)
APPLICATION_SOURCE = REPOSITORY_ROOT / "zapzap" / "app" / "application.py"
WINDOWS_ICON = (
    REPOSITORY_ROOT / "share" / "icons" / "com.rtosta.zapzap.ico"
)
README = REPOSITORY_ROOT / "README.md"


class WindowsPackagingTest(unittest.TestCase):
    def test_workflow_builds_native_x86_64_and_arm64_artifacts(self):
        workflow = WINDOWS_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("runner: windows-latest", workflow)
        self.assertIn("python_arch: x64", workflow)
        self.assertIn("artifact_arch: x86_64", workflow)
        self.assertIn("runner: windows-11-arm", workflow)
        self.assertIn("python_arch: arm64", workflow)
        self.assertIn("artifact_arch: arm64", workflow)
        self.assertIn("architecture: ${{ matrix.python_arch }}", workflow)

    def test_workflow_uses_architecture_in_build_and_upload_names(self):
        workflow = WINDOWS_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn(
            'build.ps1 -Architecture "${{ matrix.artifact_arch }}"',
            workflow,
        )
        self.assertIn("ZapZap-Windows-${{ matrix.artifact_arch }}", workflow)
        artifact_pattern = (
            "dist/ZapZap-*-windows-${{ matrix.artifact_arch }}.exe"
        )
        self.assertEqual(workflow.count(artifact_pattern), 2)
        self.assertIn("BUILD_RELEASE_TAG: ${{ inputs.release_tag }}", workflow)
        self.assertIn('"$BUILD_RELEASE_TAG"', workflow)

    def test_build_script_rejects_mismatched_python_architecture(self):
        script = WINDOWS_BUILD_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('[ValidateSet("x86_64", "arm64")]', script)
        self.assertIn("platform.machine()", script)
        self.assertIn("$RuntimeArchitecture -notin", script)
        self.assertIn(
            '"dist/ZapZap-$Version-windows-$Architecture.exe"',
            script,
        )

    def test_build_embeds_a_multiresolution_windows_icon(self):
        script = WINDOWS_BUILD_SCRIPT.read_text(encoding="utf-8")
        icon_data = WINDOWS_ICON.read_bytes()

        self.assertIn(
            '$ApplicationIcon = "share/icons/com.rtosta.zapzap.ico"',
            script,
        )
        self.assertIn('"--icon", $ApplicationIcon', script)
        self.assertEqual(icon_data[:4], b"\x00\x00\x01\x00")
        self.assertGreaterEqual(int.from_bytes(icon_data[4:6], "little"), 6)

    def test_windows_identity_is_set_before_qapplication_creation(self):
        source = APPLICATION_SOURCE.read_text(encoding="utf-8")

        identity_call = source.index("    _set_windows_app_user_model_id()")
        application_creation = source.index("    app = SingleApplication(")
        self.assertLess(identity_call, application_creation)
        self.assertIn("SetCurrentProcessExplicitAppUserModelID", source)
        self.assertIn("zapzap.__desktopid__", source)

    def test_unread_total_updates_application_and_window_icons(self):
        manager = object.__new__(SysTrayManager)
        manager._bound_window = Mock()
        app = Mock()
        icon = object()

        with (
            patch(
                "zapzap.features.tray.sys_tray_manager.IS_WINDOWS",
                True,
            ),
            patch(
                "zapzap.features.tray.sys_tray_manager.QApplication.instance",
                return_value=app,
            ),
            patch(
                "zapzap.features.tray.sys_tray_manager."
                "TrayIcon.getTaskbarIcon",
                return_value=icon,
            ) as get_icon,
        ):
            manager._set_taskbar_icon(7)
            manager._set_taskbar_icon(0)

        self.assertEqual(get_icon.call_args_list, [call(7), call(0)])
        self.assertEqual(app.setWindowIcon.call_args_list, [call(icon), call(icon)])
        self.assertEqual(
            manager._bound_window.setWindowIcon.call_args_list,
            [call(icon), call(icon)],
        )

    def test_unread_total_does_not_change_non_windows_window_icon(self):
        manager = object.__new__(SysTrayManager)
        manager._bound_window = Mock()

        with (
            patch(
                "zapzap.features.tray.sys_tray_manager.IS_WINDOWS",
                False,
            ),
            patch(
                "zapzap.features.tray.sys_tray_manager."
                "TrayIcon.getTaskbarIcon",
            ) as get_icon,
        ):
            manager._set_taskbar_icon(7)

        get_icon.assert_not_called()
        manager._bound_window.setWindowIcon.assert_not_called()

    def test_readme_lists_both_native_windows_architectures(self):
        readme = README.read_text(encoding="utf-8")

        self.assertIn("| Windows | EXE (x86_64, ARM64) |", readme)


if __name__ == "__main__":
    unittest.main()
