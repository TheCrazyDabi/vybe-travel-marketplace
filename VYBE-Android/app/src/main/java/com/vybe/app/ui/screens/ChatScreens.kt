package com.vybe.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vybe.app.data.models.ChatMessage
import com.vybe.app.data.models.Conversation
import com.vybe.app.data.repository.ChatRepository
import com.vybe.app.ui.components.EmptyState
import com.vybe.app.ui.components.ErrorState
import com.vybe.app.ui.components.LoadingState
import com.vybe.app.ui.theme.Ocean
import com.vybe.app.ui.theme.Sand
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class ChatsViewModel(private val chat: ChatRepository) : ViewModel() {
    sealed interface Ui {
        data object Loading : Ui
        data class Ready(val items: List<Conversation>) : Ui
        data class Error(val message: String) : Ui
    }

    private val _ui = MutableStateFlow<Ui>(Ui.Loading)
    val ui: StateFlow<Ui> = _ui.asStateFlow()

    fun load() {
        _ui.value = Ui.Loading
        viewModelScope.launch {
            _ui.value = try {
                Ui.Ready(chat.conversations())
            } catch (e: Exception) {
                Ui.Error("Could not load conversations.")
            }
        }
    }
}

@Composable
fun ChatsScreen(vm: ChatsViewModel, myId: Int, onOpen: (Int) -> Unit) {
    val ui by vm.ui.collectAsState()
    LaunchedEffect(Unit) { vm.load() }
    when (val s = ui) {
        is ChatsViewModel.Ui.Loading -> LoadingState("Loading chats…")
        is ChatsViewModel.Ui.Error -> ErrorState(s.message) { vm.load() }
        is ChatsViewModel.Ui.Ready -> {
            if (s.items.isEmpty()) {
                EmptyState("No conversations yet", "Express interest in a trip to start chatting.")
            } else {
                LazyColumn(
                    Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    items(s.items, key = { it.id }) { c ->
                        Card(onClick = { onOpen(c.id) }, modifier = Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text("Trip #${c.package_id ?: "—"}", fontWeight = FontWeight.Bold)
                                Text("Status: ${c.status}", color = Ocean.copy(alpha = 0.7f))
                            }
                        }
                    }
                }
            }
        }
    }
}

class ChatDetailViewModel(private val chat: ChatRepository) : ViewModel() {
    private val _messages = MutableStateFlow<List<ChatMessage>>(emptyList())
    val messages: StateFlow<List<ChatMessage>> = _messages.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()
    private val _sending = MutableStateFlow(false)
    val sending: StateFlow<Boolean> = _sending.asStateFlow()

    /** Polling refresh (web parity) with a gentle interval; stops when cleared. */
    fun start(conversationId: Int) {
        viewModelScope.launch {
            while (true) {
                try {
                    _messages.value = chat.messages(conversationId)
                    _error.value = null
                } catch (e: Exception) {
                    if (_messages.value.isEmpty()) _error.value = "Could not load messages."
                }
                delay(8000)
            }
        }
    }

    fun send(conversationId: Int, body: String, myId: Int) {
        if (body.isBlank() || _sending.value) return
        _sending.value = true
        viewModelScope.launch {
            try {
                val m = chat.send(conversationId, body.trim())
                _messages.value = _messages.value + m
                _error.value = null
            } catch (e: Exception) {
                _error.value = "Message not sent. Check connection and retry."
            }
            _sending.value = false
        }
    }
}

@Composable
fun ChatDetailScreen(vm: ChatDetailViewModel, conversationId: Int, myId: Int) {
    val messages by vm.messages.collectAsState()
    val error by vm.error.collectAsState()
    val sending by vm.sending.collectAsState()
    var draft by remember { mutableStateOf("") }
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(conversationId) { vm.start(conversationId) }
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) scope.launch { listState.animateScrollToItem(messages.size - 1) }
    }

    Column(Modifier.fillMaxSize()) {
        if (error != null && messages.isEmpty()) {
            ErrorState(error!!) { vm.start(conversationId) }
            return@Column
        }
        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            state = listState,
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(messages, key = { it.id }) { m ->
                val mine = m.sender_id == myId
                Row(Modifier.fillMaxWidth(), horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start) {
                    Card(
                        colors = androidx.compose.material3.CardDefaults.cardColors(
                            containerColor = if (mine) Ocean else Sand
                        )
                    ) {
                        Text(
                            m.body,
                            Modifier.padding(10.dp),
                            color = if (mine) androidx.compose.ui.graphics.Color.White else Ocean
                        )
                    }
                }
            }
        }
        error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(horizontal = 16.dp)) }
        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                draft, { draft = it }, Modifier.weight(1f),
                placeholder = { Text("Write a message…") }, singleLine = false, maxLines = 3
            )
            Spacer(Modifier.width(8.dp))
            Button(
                onClick = { vm.send(conversationId, draft, myId); draft = "" },
                enabled = !sending && draft.isNotBlank()
            ) { Text("Send") }
        }
    }
}
