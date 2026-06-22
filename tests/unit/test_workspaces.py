"""Tests for workspace models and API endpoints."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from fastapi import HTTPException

from backend.core.models import Workspace, WorkspaceMember
from backend.core.auth import _check_workspace_access


class TestWorkspaceModels:
    """Tests for Workspace ORM model."""

    def test_workspace_creation(self):
        """Test creating a Workspace instance."""
        workspace = Workspace(
            name="Test Workspace",
            owner_id=1,
        )
        assert workspace.name == "Test Workspace"
        assert workspace.owner_id == 1

    def test_workspace_member_creation(self):
        """Test creating a WorkspaceMember instance."""
        member = WorkspaceMember(
            workspace_id=1,
            user_id=1,
            role="owner",
        )
        assert member.workspace_id == 1
        assert member.user_id == 1
        assert member.role == "owner"

    def test_workspace_member_role_values(self):
        """Test that role accepts valid values."""
        member = WorkspaceMember(
            workspace_id=1,
            user_id=2,
            role="member",
        )
        assert member.role == "member"
        admin = WorkspaceMember(
            workspace_id=1,
            user_id=3,
            role="admin",
        )
        assert admin.role == "admin"


class TestWorkspaceAccess:
    """Tests for workspace access control functions."""

    def _make_mock_db(self):
        """Create a mock database session."""
        db = MagicMock()
        return db

    def test_access_success_for_member(self):
        """Test that access is granted for workspace member."""
        db = self._make_mock_db()
        mock_member = WorkspaceMember(
            id=1, workspace_id=1, user_id=1, role="member"
        )
        db.query.return_value.filter.return_value.first.return_value = mock_member

        member = _check_workspace_access(
            db=db, workspace_id=1, user_id=1, username="testuser"
        )
        assert member == mock_member

    def test_access_denied_for_non_member(self):
        """Test that access is denied for non-member."""
        db = self._make_mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            _check_workspace_access(
                db=db, workspace_id=1, user_id=1, username="testuser"
            )
        assert exc_info.value.status_code == 403

    def test_admin_access_owner(self):
        """Test that owner has admin access."""
        db = self._make_mock_db()
        mock_member = WorkspaceMember(
            id=1, workspace_id=1, user_id=1, role="owner"
        )
        db.query.return_value.filter.return_value.first.return_value = mock_member

        member = _check_workspace_access(
            db=db, workspace_id=1, user_id=1, username="testuser",
            required_roles=["owner", "admin"],
        )
        assert member == mock_member

    def test_admin_access_admin_role(self):
        """Test that admin has admin access."""
        db = self._make_mock_db()
        mock_member = WorkspaceMember(
            id=1, workspace_id=1, user_id=1, role="admin"
        )
        db.query.return_value.filter.return_value.first.return_value = mock_member

        member = _check_workspace_access(
            db=db, workspace_id=1, user_id=1, username="testuser",
            required_roles=["owner", "admin"],
        )
        assert member == mock_member

    def test_admin_access_member_denied(self):
        """Test that regular member is denied admin access."""
        db = self._make_mock_db()
        mock_member = WorkspaceMember(
            id=1, workspace_id=1, user_id=1, role="member"
        )
        db.query.return_value.filter.return_value.first.return_value = mock_member

        with pytest.raises(HTTPException) as exc_info:
            _check_workspace_access(
                db=db, workspace_id=1, user_id=1, username="testuser",
                required_roles=["owner", "admin"],
            )
        assert exc_info.value.status_code == 403


class TestWorkspaceSchemas:
    """Tests for Pydantic workspace schemas."""

    def test_workspace_create_schema(self):
        """Test WorkspaceCreate schema validation."""
        from backend.schemas.schemas import WorkspaceCreate

        schema = WorkspaceCreate(name="My Workspace")
        assert schema.name == "My Workspace"

    def test_workspace_response_schema(self):
        """Test WorkspaceResponse schema with from_attributes."""
        from backend.schemas.schemas import WorkspaceResponse

        schema = WorkspaceResponse(
            id=1,
            name="Test",
            owner_id=1,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert schema.id == 1
        assert schema.name == "Test"

    def test_workspace_member_add_schema(self):
        """Test WorkspaceMemberAdd schema with default role."""
        from backend.schemas.schemas import WorkspaceMemberAdd

        schema = WorkspaceMemberAdd(user_id=2)
        assert schema.user_id == 2
        assert schema.role == "member"

        schema_with_role = WorkspaceMemberAdd(user_id=3, role="admin")
        assert schema_with_role.role == "admin"
