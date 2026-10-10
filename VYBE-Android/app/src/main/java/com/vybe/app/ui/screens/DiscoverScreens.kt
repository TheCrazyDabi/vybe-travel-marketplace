package com.vybe.app.ui.screens

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.tween
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.vybe.app.data.models.TravelPackage
import com.vybe.app.discover.DeckUi
import com.vybe.app.discover.DiscoverViewModel
import com.vybe.app.ui.components.EmptyState
import com.vybe.app.ui.components.ErrorState
import com.vybe.app.ui.components.LoadingState
import com.vybe.app.ui.components.VerifiedBadge
import com.vybe.app.ui.theme.Ocean
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

@Composable
fun DiscoverScreen(vm: DiscoverViewModel, onOpenDetail: (Int) -> Unit) {
    val ui by vm.ui.collectAsState()
    LaunchedEffect(Unit) { vm.load() }
    when (val s = ui) {
        is DeckUi.Loading -> LoadingState("Finding trips for you…")
        is DeckUi.NeedsPrefs -> PrefsEditor(
            missing = s.missing,
            onSave = { fields, onErr -> vm.savePrefs(fields, {}, onErr) }
        )
        is DeckUi.Ready -> {
            val pkg = s.packages[s.index]
            var editing by remember { mutableStateOf(false) }
            val prefs by vm.prefs.collectAsState()
            if (editing) {
                PrefsEditor(
                    missing = emptyList(),
                    initialMood = prefs?.current_mood ?: "",
                    initialBudget = (prefs?.budget_per_person ?: prefs?.budget_max)?.toString() ?: "",
                    initialDuration = (prefs?.duration_days ?: 3).toString(),
                    initialRegions = (prefs?.preferred_regions ?: emptyList()).joinToString(", "),
                    initialInterests = (prefs?.interests ?: emptyList()).joinToString(", "),
                    onSave = { fields, onErr -> vm.savePrefs(fields, { editing = false }, onErr) },
                    onCancel = { editing = false }
                )
            } else {
                SwipeDeck(
                    pkg = pkg,
                    onPass = { vm.decide(pkg, "pass") },
                    onInterested = { vm.decide(pkg, "like") },
                    onLike = { on -> vm.toggleLike(pkg, on) },
                    onSave = { on -> vm.toggleSave(pkg, on) },
                    onDetail = { onOpenDetail(pkg.id) },
                    onEditPrefs = { editing = true }
                )
            }
        }
        is DeckUi.Empty -> EmptyState("All caught up!", s.message)
        is DeckUi.Error -> ErrorState(s.message) { vm.load() }
    }
}

/** Compact first-run / edit preferences form (subset of web onboarding). */
@Composable
fun PrefsEditor(
    missing: List<String>,
    initialMood: String = "",
    initialBudget: String = "",
    initialDuration: String = "3",
    initialRegions: String = "",
    initialInterests: String = "",
    onCancel: (() -> Unit)? = null,
    onSave: (Map<String, Any?>, (String) -> Unit) -> Unit
) {
    var mood by remember { mutableStateOf(initialMood) }
    var budget by remember { mutableStateOf(initialBudget) }
    var duration by remember { mutableStateOf(initialDuration) }
    var regions by remember { mutableStateOf(initialRegions) }
    var interests by remember { mutableStateOf(initialInterests) }
    var error by remember { mutableStateOf<String?>(null) }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Tell us your vibe", style = MaterialTheme.typography.headlineSmall)
        if (missing.isNotEmpty()) {
            Text("Your answers personalize the trips you see. Still needed: " + missing.joinToString(", "))
        }
        OutlinedTextField(mood, { mood = it }, Modifier.fillMaxWidth(), label = { Text("Travel mood (e.g. relaxation)") })
        OutlinedTextField(budget, { budget = it }, Modifier.fillMaxWidth(), label = { Text("Budget per person (₹)") }, singleLine = true)
        OutlinedTextField(duration, { duration = it }, Modifier.fillMaxWidth(), label = { Text("Trip duration (days)") }, singleLine = true)
        OutlinedTextField(regions, { regions = it }, Modifier.fillMaxWidth(), label = { Text("Regions (e.g. mountains, beaches)") })
        OutlinedTextField(interests, { interests = it }, Modifier.fillMaxWidth(), label = { Text("Interests (e.g. nature, food)") })
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Button(onClick = {
            val fields = mutableMapOf<String, Any?>()
            if (mood.isNotBlank()) fields["current_mood"] = mood.trim()
            budget.toIntOrNull()?.let { fields["budget_max"] = it; fields["budget_per_person"] = it }
            duration.toIntOrNull()?.let { fields["duration_days"] = it }
            if (regions.isNotBlank()) fields["preferred_regions"] = regions.split(",").map { it.trim() }.filter { it.isNotEmpty() }
            if (interests.isNotBlank()) fields["interests"] = interests.split(",").map { it.trim() }.filter { it.isNotEmpty() }
            onSave(fields) { error = it }
        }, modifier = Modifier.fillMaxWidth()) { Text("Save & discover") }
        onCancel?.let { OutlinedButton(onClick = it, modifier = Modifier.fillMaxWidth()) { Text("Cancel") } }
    }
}

@Composable
fun SwipeDeck(
    pkg: TravelPackage,
    onPass: () -> Unit,
    onInterested: () -> Unit,
    onLike: (Boolean) -> Unit,
    onSave: (Boolean) -> Unit,
    onDetail: () -> Unit,
    onEditPrefs: () -> Unit
) {
    val scope = rememberCoroutineScope()
    val offsetX = remember(pkg.id) { Animatable(0f) }
    var liked by remember(pkg.id) { mutableStateOf(false) }
    var saved by remember(pkg.id) { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Box(
            Modifier.weight(1f).fillMaxWidth()
                .offset { IntOffset(offsetX.value.roundToInt(), 0) }
                .rotate(offsetX.value / 40f)
                .pointerInput(pkg.id) {
                    detectDragGestures(
                        onDragEnd = {
                            scope.launch {
                                when {
                                    offsetX.value > 220f -> {
                                        offsetX.animateTo(900f, tween(180)); onInterested()
                                    }
                                    offsetX.value < -220f -> {
                                        offsetX.animateTo(-900f, tween(180)); onPass()
                                    }
                                    else -> offsetX.animateTo(0f, tween(180))
                                }
                            }
                        }
                    ) { _, dragAmount ->
                        scope.launch { offsetX.snapTo(offsetX.value + dragAmount.x) }
                    }
                }
        ) {
            PackageCard(pkg, { onOpenDetail() })
        }
        Spacer(Modifier.height(12.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly, verticalAlignment = Alignment.CenterVertically) {
            OutlinedButton(onClick = onPass) { Text("✕ Pass") }
            OutlinedButton(onClick = { liked = !liked; onLike(liked) }) { Text(if (liked) "♥" else "♡") }
            Button(onClick = onInterested) { Text("♥ Interested") }
            OutlinedButton(onClick = { saved = !saved; onSave(saved) }) { Text(if (saved) "★" else "☆") }
        }
        Spacer(Modifier.height(8.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
            OutlinedButton(onClick = onDetail) { Text("Details") }
            OutlinedButton(onClick = onEditPrefs) { Text("Edit preferences") }
        }
    }
}

@Composable
fun PackageCard(pkg: TravelPackage, onClick: () -> Unit) {
    Card(
        onClick = onClick,
        modifier = Modifier.fillMaxSize(),
        shape = RoundedCornerShape(22.dp),
        elevation = CardDefaults.cardElevation(8.dp)
    ) {
        Column {
            AsyncImage(
                model = pkg.cover_image,
                contentDescription = pkg.destination,
                modifier = Modifier.fillMaxWidth().height(280.dp),
                contentScale = ContentScale.Crop
            )
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(pkg.title, style = MaterialTheme.typography.titleMedium)
                Text(
                    "${pkg.destination} · ${pkg.duration_days} days · ₹${pkg.price}",
                    color = Ocean.copy(alpha = 0.7f)
                )
                pkg.operator?.let {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("by ${it.company_name}  ", fontWeight = FontWeight.SemiBold)
                        VerifiedBadge(it.is_verified)
                    }
                }
                pkg.match_score?.let {
                    Text("★ ${it.toInt()} match", fontWeight = FontWeight.Bold, color = Ocean)
                }
                pkg.match_reasons.firstOrNull()?.let { Text(it) }
            }
        }
    }
}
