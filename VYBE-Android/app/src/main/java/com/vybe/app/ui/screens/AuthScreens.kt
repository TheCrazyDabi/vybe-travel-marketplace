package com.vybe.app.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vybe.app.auth.AuthUi
import com.vybe.app.auth.AuthViewModel
import com.vybe.app.data.models.User
import com.vybe.app.ui.theme.Ocean

@Composable
fun LoginScreen(vm: AuthViewModel, onLoggedIn: (User) -> Unit, onRegister: () -> Unit, onServer: () -> Unit) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var shown by remember { mutableStateOf(false) }
    val state by vm.state.collectAsState()
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp)
    ) {
        Text("✦ VYBE", fontSize = 30.sp, fontWeight = FontWeight.Black, color = Ocean)
        Text("Find trips that match your vibe.", style = MaterialTheme.typography.bodyLarge)
        Spacer(Modifier.height(24.dp))
        OutlinedTextField(email, { email = it }, Modifier.fillMaxWidth(), label = { Text("Email") }, singleLine = true)
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            password, { password = it }, Modifier.fillMaxWidth(), label = { Text("Password") },
            singleLine = true,
            visualTransformation = if (shown) VisualTransformation.None else PasswordVisualTransformation(),
            trailingIcon = { TextButton(onClick = { shown = !shown }) { Text(if (shown) "Hide" else "Show") } }
        )
        if (state is AuthUi.Error) {
            Spacer(Modifier.height(8.dp))
            Text((state as AuthUi.Error).message, color = MaterialTheme.colorScheme.error)
        }
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = { vm.login(email, password, onLoggedIn) },
            modifier = Modifier.fillMaxWidth(),
            enabled = state != AuthUi.Busy
        ) {
            if (state == AuthUi.Busy) CircularProgressIndicator() else Text("Log in")
        }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(onClick = onRegister, modifier = Modifier.fillMaxWidth()) { Text("Create account") }
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = onServer) { Text("Server settings") }
    }
}

@Composable
fun RegisterScreen(vm: AuthViewModel, onDone: (User) -> Unit, onLogin: () -> Unit) {
    var name by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var shown by remember { mutableStateOf(false) }
    var role by remember { mutableStateOf("traveler") }
    val state by vm.state.collectAsState()
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp)
    ) {
        Text("Join VYBE", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(16.dp))
        OutlinedTextField(name, { name = it }, Modifier.fillMaxWidth(), label = { Text("Name") }, singleLine = true)
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(email, { email = it }, Modifier.fillMaxWidth(), label = { Text("Email") }, singleLine = true)
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            password, { password = it }, Modifier.fillMaxWidth(), label = { Text("Password (6+ chars)") },
            singleLine = true,
            visualTransformation = if (shown) VisualTransformation.None else PasswordVisualTransformation(),
            trailingIcon = { TextButton(onClick = { shown = !shown }) { Text(if (shown) "Hide" else "Show") } }
        )
        Spacer(Modifier.height(12.dp))
        Text("I am a:", fontWeight = FontWeight.Bold)
        RoleRow(role) { role = it }
        if (state is AuthUi.Error) {
            Spacer(Modifier.height(8.dp))
            Text((state as AuthUi.Error).message, color = MaterialTheme.colorScheme.error)
        }
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = { vm.register(name, email, password, role, onDone) },
            modifier = Modifier.fillMaxWidth(),
            enabled = state != AuthUi.Busy
        ) {
            if (state == AuthUi.Busy) CircularProgressIndicator() else Text("Create account")
        }
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = onLogin) { Text("Have an account? Log in") }
    }
}

@Composable
private fun RoleRow(role: String, onPick: (String) -> Unit) {
    Column {
        listOf("traveler" to "Traveler — discover trips", "operator" to "Travel operator — publish packages").forEach { (v, label) ->
            TextButton(onClick = { onPick(v) }) {
                Text(if (v == role) "● $label" else "○ $label")
            }
        }
    }
}

@Composable
fun ServerScreen(vm: AuthViewModel, current: String, onSaved: () -> Unit) {
    var url by remember(current) { mutableStateOf(current) }
    val state by vm.state.collectAsState()
    Column(Modifier.fillMaxSize().padding(24.dp)) {
        Text("Server address", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(8.dp))
        Text("Emulator: http://10.0.2.2:5000 · Phone on same Wi-Fi: http://<laptop-ip>:5000 · Remote: your ngrok https URL.")
        Spacer(Modifier.height(16.dp))
        OutlinedTextField(url, { url = it }, Modifier.fillMaxWidth(), label = { Text("API base URL") }, singleLine = true)
        if (state is AuthUi.Error) {
            Spacer(Modifier.height(8.dp))
            Text((state as AuthUi.Error).message, color = MaterialTheme.colorScheme.error)
        }
        Spacer(Modifier.height(16.dp))
        Button(onClick = { vm.saveServer(url, onSaved) }, modifier = Modifier.fillMaxWidth()) { Text("Save") }
    }
}
