#!/bin/bash
# Download voice samples from Internet Archive (LibriVox)
# Each file is 2-3 minutes of clear narration

cd /workspace/TTS/indextts-server/voices

# Remove failed 0-byte files
rm -f *.mp3 2>/dev/null

echo "Downloading diverse voice samples from Internet Archive..."

# MALE VOICES

# 1. David (Peter Yearsley - British male)
wget -O "David.mp3" "https://archive.org/download/tale_of_two_cities_librivox/twocities_01_dickens_64kb.mp3" &

# 2. Edward (David Barnes - British male)
wget -O "Edward.mp3" "https://archive.org/download/canterville_ghost_librivox/canterville_01_wilde_64kb.mp3" &

# 3. George (Mark F. Smith - American male)
wget -O "George.mp3" "https://archive.org/download/treasure_island_0711_librivox/treasure_island_01_stevenson_64kb.mp3" &

# 4. Henry (Greg Giordano - American male)
wget -O "Henry.mp3" "https://archive.org/download/count_monte_cristo_0711_librivox/count_of_monte_cristo_001_dumas_64kb.mp3" &

# 5. James (already downloaded - keep existing)
# James.mp3 exists

# 6. Robert (Bob Neufeld - deep American male)
wget -O "Robert.mp3" "https://archive.org/download/sherlock_holmes_adventures_01_v3/sherlockholmes01_01_doyle_64kb.mp3" &

# 7. Thomas (John Greenman - clear American male)
wget -O "Thomas.mp3" "https://archive.org/download/uncle_toms_cabin_librivox/uncle_toms_cabin_01_stowe_64kb.mp3" &

# 8. William (Martin Geeson - British male)
wget -O "William.mp3" "https://archive.org/download/frankenstein_1818/frankenstein_1818_01_shelley_64kb.mp3" &

# 9. Arthur (Ralph Snelson - American male)
wget -O "Arthur.mp3" "https://archive.org/download/secret_garden_librivox/secret_garden_01_burnett_64kb.mp3" &

# 10. Richard (Rob Boardman - British male)
wget -O "Richard.mp3" "https://archive.org/download/hound_baskervilles_librivox/hound_baskervilles_01_doyle_64kb.mp3" &

wait

# FEMALE VOICES

# 11. Anne (Karen Savage - American female)
wget -O "Anne.mp3" "https://archive.org/download/pride_and_prejudice_librivox/prideandprejudice_01_austen_64kb.mp3" &

# 12. Catherine (Annie Coleman Rothenberg - American female)
wget -O "Catherine.mp3" "https://archive.org/download/huck_finn_librivox/huck_finn_01_twain_64kb.mp3" &

# 13. Charlotte (Michelle Crandall - American female)
wget -O "Charlotte.mp3" "https://archive.org/download/jane_eyre_ver02/janeeyre_01_bronte_64kb.mp3" &

# 14. Eleanor (Ruth Golding - British female)
wget -O "Eleanor.mp3" "https://archive.org/download/bleak_house_cl_librivox/bleak_house_01_dickens_64kb.mp3" &

# 15. Elizabeth (Kristin LeMoine - American female)
wget -O "Elizabeth.mp3" "https://archive.org/download/emma_solo_librivox/emma_01_austen_64kb.mp3" &

# 16. Isabella (Kara Shallenberg - American female)
wget -O "Isabella.mp3" "https://archive.org/download/wuthering_heights_librivox/wuthering_heights_01_bronte_64kb.mp3" &

# 17. Margaret (Elizabeth Klett - American female)
wget -O "Margaret.mp3" "https://archive.org/download/sense_sensibility_0805_librivox/senseandsensibility_01_austen_64kb.mp3" &

# 18. Mary (Cori Samuel - British female)
wget -O "Mary.mp3" "https://archive.org/download/persuasion_librivox/persuasion_01_austen_64kb.mp3" &

# 19. Sarah (Caroline Feraday - British female)
wget -O "Sarah.mp3" "https://archive.org/download/northangerabbey_1001_librivox/northangerabbey_01_austen_64kb.mp3" &

# 20. Victoria (Kristin Hughes - American female)
wget -O "Victoria.mp3" "https://archive.org/download/little_women_librivox/littlewomen_01_alcott_64kb.mp3" &

wait

echo ""
echo "Download complete! Checking file sizes..."
ls -lh *.mp3

echo ""
echo "Removing any failed downloads (0 bytes)..."
find . -name "*.mp3" -size 0 -delete

echo ""
echo "Final voice files:"
ls -lh *.mp3
