package com.vybe.app.discover

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vybe.app.data.api.ApiError
import com.vybe.app.data.api.NetworkError
import com.vybe.app.data.models.TravelPackage
import com.vybe.app.data.models.TravelerProfile
import com.vybe.app.data.repository.TravelRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface DeckUi {
    data object Loading : DeckUi
    /** Prefs incomplete: must complete before the deck shows (web parity). */
    data class NeedsPrefs(val missing: List<String>) : DeckUi
    data class Ready(val packages: List<TravelPackage>, val index: Int) : DeckUi
    data class Empty(val message: String) : DeckUi
    data class Error(val message: String) : DeckUi
}

class DiscoverViewModel(private val travel: TravelRepository) : ViewModel() {
    private val _ui = MutableStateFlow<DeckUi>(DeckUi.Loading)
    val ui: StateFlow<DeckUi> = _ui.asStateFlow()

    private val _prefs = MutableStateFlow<TravelerProfile?>(null)
    val prefs: StateFlow<TravelerProfile?> = _prefs.asStateFlow()

    fun load() {
        _ui.value = DeckUi.Loading
        viewModelScope.launch {
            _ui.value = try {
                val (_, profile) = travel.profile()
                _prefs.value = profile
                val missing = profile.missingRequired()
                if (missing.isNotEmpty()) {
                    DeckUi.NeedsPrefs(missing)
                } else {
                    val (pkgs, _) = travel.recommended()
                    if (pkgs.isEmpty()) DeckUi.Empty("No more packages right now. Try different preferences.")
                    else DeckUi.Ready(pkgs, 0)
                }
            } catch (e: ApiError) {
                DeckUi.Error(e.message ?: "Server error.")
            } catch (e: NetworkError) {
                DeckUi.Error("No connection to the VYBE server.")
            }
        }
    }

    fun savePrefs(fields: Map<String, Any?>, onSaved: () -> Unit, onError: (String) -> Unit) {
        viewModelScope.launch {
            try {
                val (_, profile) = travel.updateProfile(fields)
                _prefs.value = profile
                val missing = profile.missingRequired()
                if (missing.isNotEmpty()) {
                    onError("Still needed: " + missing.joinToString(", "))
                } else {
                    onSaved()
                    load()
                }
            } catch (e: ApiError) {
                onError(e.message ?: "Save failed.")
            } catch (e: NetworkError) {
                onError("No connection to the VYBE server.")
            }
        }
    }

    /** Records a decision; only advances the queue on success (no silent loss). */
    fun decide(pkg: TravelPackage, action: String) {
        val cur = (_ui.value as? DeckUi.Ready) ?: return
        viewModelScope.launch {
            try {
                travel.swipe(pkg.id, action)
                advance(cur)
            } catch (e: Exception) {
                _ui.value = DeckUi.Error("Could not record decision. Check connection.")
            }
        }
    }

    fun toggleLike(pkg: TravelPackage, on: Boolean) {
        viewModelScope.launch {
            try {
                travel.like(pkg.id, on)
            } catch (e: Exception) {
                _ui.value = DeckUi.Error("Could not update favourite.")
            }
        }
    }

    fun toggleSave(pkg: TravelPackage, on: Boolean) {
        viewModelScope.launch {
            try {
                travel.save(pkg.id, on)
            } catch (e: Exception) {
                _ui.value = DeckUi.Error("Could not update saved list.")
            }
        }
    }

    private fun advance(cur: DeckUi.Ready) {
        val next = cur.index + 1
        _ui.value = if (next >= cur.packages.size) {
            DeckUi.Empty("All caught up! No more packages right now.")
        } else {
            cur.copy(index = next)
        }
    }
}
