package com.vybe.app.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vybe.app.data.api.ApiError
import com.vybe.app.data.api.NetworkError
import com.vybe.app.data.api.SettingsStore
import com.vybe.app.data.models.User
import com.vybe.app.data.repository.SessionRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface AuthUi {
    data object Idle : AuthUi
    data object Busy : AuthUi
    data class Error(val message: String) : AuthUi
}

class AuthViewModel(
    private val session: SessionRepository,
    private val settings: SettingsStore
) : ViewModel() {
    val user: StateFlow<User?> = session.user

    private val _state = MutableStateFlow<AuthUi>(AuthUi.Idle)
    val state: StateFlow<AuthUi> = _state.asStateFlow()

    fun login(email: String, password: String, onDone: (User) -> Unit) {
        if (email.isBlank() || password.isBlank()) {
            _state.value = AuthUi.Error("Email and password are required.")
            return
        }
        _state.value = AuthUi.Busy
        viewModelScope.launch {
            _state.value = try {
                val u = session.login(email, password)
                onDone(u)
                AuthUi.Idle
            } catch (e: ApiError) {
                AuthUi.Error(if (e.status == 401) "Invalid email or password." else e.message ?: "Login failed.")
            } catch (e: NetworkError) {
                AuthUi.Error("Cannot reach the server. Check the server address and connection.")
            }
        }
    }

    fun register(name: String, email: String, password: String, role: String, onDone: (User) -> Unit) {
        if (name.isBlank() || email.isBlank() || password.length < 6) {
            _state.value = AuthUi.Error("Name, valid email and 6+ character password required.")
            return
        }
        _state.value = AuthUi.Busy
        viewModelScope.launch {
            _state.value = try {
                val u = session.register(name, email, password, if (role == "operator") "operator" else "traveler")
                onDone(u)
                AuthUi.Idle
            } catch (e: ApiError) {
                AuthUi.Error(e.message ?: "Registration failed.")
            } catch (e: NetworkError) {
                AuthUi.Error("Cannot reach the server. Check the server address and connection.")
            }
        }
    }

    fun logout(onDone: () -> Unit) {
        viewModelScope.launch {
            session.logout()
            onDone()
        }
    }

    /** Returns true when a live server session was restored. */
    suspend fun restore(): Boolean {
        return try {
            session.refresh() != null
        } catch (e: Exception) {
            false
        }
    }

    fun saveServer(url: String, onDone: () -> Unit) {
        val clean = url.trim()
        if (!clean.startsWith("http://") && !clean.startsWith("https://")) {
            _state.value = AuthUi.Error("Server URL must start with http:// or https://")
            return
        }
        viewModelScope.launch {
            settings.setBaseUrl(clean)
            onDone()
        }
    }
}
