package com.vybe.app

import com.vybe.app.data.models.TravelerProfile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Pure-logic tests: no Android framework, no network. */
class LogicTest {

    @Test
    fun prefsMissingDetectsEmpty() {
        val p = TravelerProfile()
        assertEquals(
            listOf("travel mood", "budget per person", "trip duration", "destinations or regions"),
            p.missingRequired()
        )
    }

    @Test
    fun prefsMissingAcceptsApiSavedShape() {
        val p = TravelerProfile(
            current_mood = "relaxation",
            budget_max = 15000,
            duration_days = 3,
            preferred_regions = listOf("mountains")
        )
        assertTrue(p.missingRequired().isEmpty())
    }

    @Test
    fun prefsMissingAcceptsPerPersonBudget() {
        val p = TravelerProfile(
            travel_moods = listOf("Adventure"),
            budget_per_person = 12000,
            duration_days = 4,
            destination_prefs = listOf("Goa")
        )
        assertTrue(p.missingRequired().isEmpty())
    }
}
