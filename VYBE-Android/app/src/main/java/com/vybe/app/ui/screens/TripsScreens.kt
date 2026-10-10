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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vybe.app.data.models.Booking
import com.vybe.app.data.models.Enquiry
import com.vybe.app.data.repository.TripsRepository
import com.vybe.app.ui.components.EmptyState
import com.vybe.app.ui.components.ErrorState
import com.vybe.app.ui.components.LoadingState
import com.vybe.app.ui.theme.Ocean
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class TripsViewModel(private val trips: TripsRepository) : ViewModel() {
    sealed interface Ui {
        data object Loading : Ui
        data class Ready(val enquiries: List<Enquiry>, val bookings: List<Booking>) : Ui
        data class Error(val message: String) : Ui
    }

    private val _ui = MutableStateFlow<Ui>(Ui.Loading)
    val ui: StateFlow<Ui> = _ui.asStateFlow()

    fun load() {
        _ui.value = Ui.Loading
        viewModelScope.launch {
            _ui.value = try {
                Ui.Ready(trips.enquiries(), trips.bookings())
            } catch (e: Exception) {
                Ui.Error("Could not load your trips. Check connection.")
            }
        }
    }
}

/** My Trips mirrors the web dashboard: interests become enquiries,
 *  operator quotes advance them, confirmed ones become bookings.
 *  No states are invented — everything comes from the server. */
@Composable
fun TripsScreen(vm: TripsViewModel) {
    val ui by vm.ui.collectAsState()
    LaunchedEffect(Unit) { vm.load() }
    when (val s = ui) {
        is TripsViewModel.Ui.Loading -> LoadingState("Loading your trips…")
        is TripsViewModel.Ui.Error -> ErrorState(s.message) { vm.load() }
        is TripsViewModel.Ui.Ready -> {
            if (s.enquiries.isEmpty() && s.bookings.isEmpty()) {
                EmptyState("No trips yet", "Swipe right on Discover to start an enquiry.")
            } else {
                LazyColumn(
                    Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    if (s.bookings.isNotEmpty()) {
                        item { Text("Bookings", style = MaterialTheme.typography.titleMedium) }
                    }
                    items(s.bookings, key = { "b${it.id}" }) { b ->
                        TripCard(
                            title = b.pkg?.title ?: "Trip #${b.package_id}",
                            subtitle = "Booking ${b.status} · ${b.payment_status ?: ""}",
                            detail = b.total_cost?.let { "Total ₹$it" } ?: ""
                        )
                    }
                    if (s.enquiries.isNotEmpty()) {
                        item { Text("Enquiries", style = MaterialTheme.typography.titleMedium) }
                    }
                    items(s.enquiries, key = { "e${it.id}" }) { e ->
                        val quote = e.quotations.firstOrNull { it.status == "sent" }
                        TripCard(
                            title = e.pkg?.title ?: "Trip #${e.package_id}",
                            subtitle = "Status: ${e.status.replace('_', ' ')}",
                            detail = quote?.let { "Quoted ₹${it.total_price ?: it.price_per_person}/person" } ?: ""
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun TripCard(title: String, subtitle: String, detail: String) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, fontWeight = FontWeight.Bold)
            Text(subtitle, color = Ocean.copy(alpha = 0.7f))
            if (detail.isNotBlank()) Text(detail, fontWeight = FontWeight.SemiBold)
        }
    }
}
