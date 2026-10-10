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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import coil.compose.AsyncImage
import com.vybe.app.data.models.Interest
import com.vybe.app.data.models.TravelPackage
import com.vybe.app.data.repository.TravelRepository
import com.vybe.app.ui.components.EmptyState
import com.vybe.app.ui.components.ErrorState
import com.vybe.app.ui.components.LoadingState
import com.vybe.app.ui.components.VerifiedBadge
import com.vybe.app.ui.theme.Ocean
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class ExploreViewModel(private val travel: TravelRepository) : ViewModel() {
    sealed interface Ui {
        data object Loading : Ui
        data class Ready(val packages: List<TravelPackage>) : Ui
        data class Error(val message: String) : Ui
    }

    private val _ui = MutableStateFlow<Ui>(Ui.Loading)
    val ui: StateFlow<Ui> = _ui.asStateFlow()

    fun load() {
        _ui.value = Ui.Loading
        viewModelScope.launch {
            _ui.value = try {
                Ui.Ready(travel.packages())
            } catch (e: Exception) {
                Ui.Error("Could not load trips. Check connection.")
            }
        }
    }
}

@Composable
fun ExploreScreen(vm: ExploreViewModel, onOpen: (Int) -> Unit) {
    val ui by vm.ui.collectAsState()
    LaunchedEffect(Unit) { vm.load() }
    when (val s = ui) {
        is ExploreViewModel.Ui.Loading -> LoadingState("Loading trips…")
        is ExploreViewModel.Ui.Error -> ErrorState(s.message) { vm.load() }
        is ExploreViewModel.Ui.Ready -> {
            if (s.packages.isEmpty()) {
                EmptyState("No trips yet", "Approved packages will appear here.")
            } else {
                LazyColumn(
                    Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    items(s.packages, key = { it.id }) { pkg ->
                        ExploreRow(pkg) { onOpen(pkg.id) }
                    }
                }
            }
        }
    }
}

@Composable
fun ExploreRow(pkg: TravelPackage, onClick: () -> Unit) {
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            AsyncImage(
                model = pkg.cover_image,
                contentDescription = pkg.destination,
                modifier = Modifier.width(96.dp).height(96.dp),
                contentScale = ContentScale.Crop
            )
            Spacer(Modifier.width(12.dp))
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(pkg.title, fontWeight = FontWeight.Bold)
                Text("${pkg.destination} · ${pkg.duration_days} days · ₹${pkg.price}",
                    color = Ocean.copy(alpha = 0.7f))
                pkg.operator?.let { VerifiedBadge(it.is_verified) }
            }
        }
    }
}

class DetailViewModel(private val travel: TravelRepository) : ViewModel() {
    sealed interface Ui {
        data object Loading : Ui
        data class Ready(val pkg: TravelPackage) : Ui
        data class Error(val message: String) : Ui
    }

    private val _ui = MutableStateFlow<Ui>(Ui.Loading)
    val ui: StateFlow<Ui> = _ui.asStateFlow()

    fun load(id: Int) {
        _ui.value = Ui.Loading
        viewModelScope.launch {
            _ui.value = try {
                Ui.Ready(travel.detail(id))
            } catch (e: Exception) {
                Ui.Error("Could not load this trip.")
            }
        }
    }

    fun interested(id: Int, onDone: (Boolean) -> Unit) {
        viewModelScope.launch {
            try {
                // Interested = enquiry intent only, never a booking (web parity).
                travel.swipe(id, "like")
                onDone(true)
            } catch (e: Exception) {
                onDone(false)
            }
        }
    }
}

@Composable
fun DetailScreen(vm: DetailViewModel, packageId: Int, onChatHint: () -> Unit) {
    val ui by vm.ui.collectAsState()
    var msg by remember(packageId) { mutableStateOf<String?>(null) }
    LaunchedEffect(packageId) { vm.load(packageId) }
    when (val s = ui) {
        is DetailViewModel.Ui.Loading -> LoadingState()
        is DetailViewModel.Ui.Error -> ErrorState(s.message) { vm.load(packageId) }
        is DetailViewModel.Ui.Ready -> {
            val p = s.pkg
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)) {
                AsyncImage(
                    model = p.cover_image, contentDescription = p.destination,
                    modifier = Modifier.fillMaxWidth().height(240.dp), contentScale = ContentScale.Crop
                )
                Text(p.title, style = MaterialTheme.typography.headlineSmall)
                Text("${p.destination} · ${p.duration_days} days · ₹${p.price}",
                    fontWeight = FontWeight.Bold, color = Ocean)
                p.operator?.let {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("by ${it.company_name}  ")
                        VerifiedBadge(it.is_verified)
                    }
                }
                p.short_desc?.let { Text(it) }
                p.itinerary?.let { Text(it, color = Ocean.copy(alpha = 0.8f)) }
                msg?.let { Text(it) }
                Button(onClick = { vm.interested(p.id) { ok ->
                    msg = if (ok) "Interest recorded — the operator can now see it." else "Failed. Check connection."
                } }, modifier = Modifier.fillMaxWidth()) { Text("♥ I'm interested") }
                OutlinedButton(onClick = onChatHint, modifier = Modifier.fillMaxWidth()) {
                    Text("Chat with operator (web app for now)")
                }
            }
        }
    }
}

class SavedViewModel(private val travel: TravelRepository) : ViewModel() {
    sealed interface Ui {
        data object Loading : Ui
        data class Ready(val items: List<Interest>) : Ui
        data class Error(val message: String) : Ui
    }

    private val _ui = MutableStateFlow<Ui>(Ui.Loading)
    val ui: StateFlow<Ui> = _ui.asStateFlow()

    fun load() {
        _ui.value = Ui.Loading
        viewModelScope.launch {
            _ui.value = try {
                Ui.Ready(travel.interests())
            } catch (e: Exception) {
                Ui.Error("Could not load saved trips.")
            }
        }
    }
}

@Composable
fun SavedScreen(vm: SavedViewModel, onOpen: (Int) -> Unit) {
    val ui by vm.ui.collectAsState()
    LaunchedEffect(Unit) { vm.load() }
    when (val s = ui) {
        is SavedViewModel.Ui.Loading -> LoadingState()
        is SavedViewModel.Ui.Error -> ErrorState(s.message) { vm.load() }
        is SavedViewModel.Ui.Ready -> {
            if (s.items.isEmpty()) {
                EmptyState("Nothing saved yet", "Swipe right or tap ☆ on Discover.")
            } else {
                LazyColumn(
                    Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    items(s.items, key = { it.id }) { interest ->
                        val pkg = interest.pkg
                        if (pkg != null) ExploreRow(pkg) { onOpen(pkg.id) }
                    }
                }
            }
        }
    }
}
