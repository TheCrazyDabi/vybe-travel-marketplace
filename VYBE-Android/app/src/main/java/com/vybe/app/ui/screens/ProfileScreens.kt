package com.vybe.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vybe.app.data.models.TravelerProfile
import com.vybe.app.data.models.User
import com.vybe.app.data.repository.TravelRepository
import com.vybe.app.ui.components.EmptyState
import com.vybe.app.ui.components.ErrorState
import com.vybe.app.ui.components.LoadingState
import com.vybe.app.ui.theme.Coral
import com.vybe.app.ui.theme.Ocean
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class ProfileViewModel(private val travel: TravelRepository) : ViewModel() {
    sealed interface Ui {
        data object Loading : Ui
        data class Ready(val user: User, val profile: TravelerProfile) : Ui
        data class Error(val message: String) : Ui
    }

    private val _ui = MutableStateFlow<Ui>(Ui.Loading)
    val ui: StateFlow<Ui> = _ui.asStateFlow()
    private val _notice = MutableStateFlow<String?>(null)
    val notice: StateFlow<String?> = _notice.asStateFlow()

    fun load() {
        _ui.value = Ui.Loading
        viewModelScope.launch {
            _ui.value = try {
                val (u, p) = travel.profile()
                Ui.Ready(u, p)
            } catch (e: Exception) {
                Ui.Error("Could not load profile.")
            }
        }
    }

    /** Only name + departure city are server-persisted (web parity);
     *  phone/bio stay demo-local like the website. */
    fun saveNameCity(name: String, city: String) {
        viewModelScope.launch {
            try {
                if (name.isBlank()) {
                    _notice.value = "Name is required."
                    return@launch
                }
                val (u, p) = travel.updateProfile(mapOf("name" to name.trim(), "start_city" to city.trim()))
                _ui.value = Ui.Ready(u, p)
                _notice.value = "Saved to your account."
            } catch (e: Exception) {
                _notice.value = "Could not save. Check connection."
            }
        }
    }
}

/** Profile = personal account info only (web parity). Preferences live on Discover. */
@Composable
fun ProfileScreen(vm: ProfileViewModel, onLogout: () -> Unit) {
    val ui by vm.ui.collectAsState()
    val notice by vm.notice.collectAsState()
    LaunchedEffect(Unit) { vm.load() }
    when (val s = ui) {
        is ProfileViewModel.Ui.Loading -> LoadingState()
        is ProfileViewModel.Ui.Error -> ErrorState(s.message) { vm.load() }
        is ProfileViewModel.Ui.Ready -> {
            var name by remember(s.user.id) { mutableStateOf(s.user.name) }
            var city by remember(s.user.id) { mutableStateOf(s.profile.start_city ?: "") }
            var phone by remember(s.user.id) { mutableStateOf("") }
            var bio by remember(s.user.id) { mutableStateOf("") }
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        Modifier.size(64.dp).clip(CircleShape).background(Coral),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            s.user.name.split(" ").take(2).mapNotNull { it.firstOrNull()?.uppercase() }.joinToString(""),
                            fontSize = 24.sp, fontWeight = FontWeight.Black, color = Ocean
                        )
                    }
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text(s.user.name, style = MaterialTheme.typography.titleMedium)
                        Text(s.user.email)
                        Text(s.user.role.replaceFirstChar { it.uppercase() })
                    }
                }
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("Personal information", style = MaterialTheme.typography.titleMedium)
                        OutlinedTextField(name, { name = it }, Modifier.fillMaxWidth(), label = { Text("Full name") }, singleLine = true)
                        OutlinedTextField(s.user.email, {}, Modifier.fillMaxWidth(), label = { Text("Email (read-only)") }, enabled = false, singleLine = true)
                        OutlinedTextField(phone, { phone = it }, Modifier.fillMaxWidth(), label = { Text("Phone (demo, this device only)") }, singleLine = true)
                        OutlinedTextField(city, { city = it }, Modifier.fillMaxWidth(), label = { Text("Home / departure city") }, singleLine = true)
                        OutlinedTextField(bio, { bio = it }, Modifier.fillMaxWidth(), label = { Text("Travel bio (demo, this device only)") })
                        notice?.let { Text(it) }
                        Button(onClick = { vm.saveNameCity(name, city) }, modifier = Modifier.fillMaxWidth()) {
                            Text("Save Changes")
                        }
                    }
                }
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text("Account settings", style = MaterialTheme.typography.titleMedium)
                        Text("Password: •••••••• (changes disabled in this demo)")
                        Text("Member since ${s.user.created_at?.take(10) ?: "—"}")
                        OutlinedButton(onClick = onLogout, modifier = Modifier.fillMaxWidth()) { Text("Sign Out") }
                    }
                }
            }
        }
    }
}
