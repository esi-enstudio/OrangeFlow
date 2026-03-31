import re

def validate_and_expand_serials(text_input: str, max_limit: int = 50):
    """
    সিম সিরিয়াল ভ্যালিডেশন এবং রেঞ্জ এক্সপান্ড করার গ্লোবাল লজিক।
    রিটার্ন করে: (valid_serials, invalid_lines, error_message)
    """
    raw_lines = [line.strip() for line in text_input.strip().split("\n") if line.strip()]
    final_serials = []
    invalid_lines = []
    error_message = None

    for line in raw_lines:
        # ১. সাধারণ ১৮-২০ ডিজিট সিরিয়াল চেক
        if re.fullmatch(r'\d{18,20}', line):
            final_serials.append(line)
        
        # ২. রেঞ্জ চেক (উদা: 898803991849230687-690)
        elif "-" in line:
            parts = line.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                start_full = parts[0]
                end_suffix = parts[1]
                
                # সাফিক্সের দৈর্ঘ্য অনুযায়ী প্রিফিক্স আলাদা করা
                suffix_len = len(end_suffix)
                if len(start_full) >= suffix_len:
                    start_suffix = start_full[-suffix_len:]
                    prefix = start_full[:-suffix_len]

                    try:
                        start_num = int(start_suffix)
                        end_num = int(end_suffix)

                        if start_num <= end_num:
                            # রেঞ্জ এক্সপান্ড করা
                            for i in range(start_num, end_num + 1):
                                new_suffix = str(i).zfill(suffix_len)
                                final_serials.append(prefix + new_suffix)
                        else:
                            invalid_lines.append(line)
                    except:
                        invalid_lines.append(line)
                else:
                    invalid_lines.append(line)
            else:
                invalid_lines.append(line)
        else:
            invalid_lines.append(line)

    # ৩. ডুপ্লিকেট রিমুভ করা
    final_serials = list(dict.fromkeys(final_serials))

    # ৪. লিমিট চেক এবং এরর মেসেজ তৈরি
    if invalid_lines:
        error_message = "⚠️ **ভুল ফরম্যাট ডিটেক্ট হয়েছে!**\n\n"
        for err in invalid_lines:
            error_message += f"❌ `{err}`\n"
        error_message += "\n**সঠিক উদাহরণ:**\n`898803991849230680` (একটি)\n`898803991849230687-690` (রেঞ্জ)"
    
    elif len(final_serials) > max_limit:
        error_message = f"⚠️ আপনি একসাথে {len(final_serials)}টি সিম দিয়েছেন। দয়া করে সর্বোচ্চ {max_limit}টি সিম একবারে দিন।"
    
    elif not final_serials:
        error_message = "⚠️ কোনো বৈধ সিম সিরিয়াল পাওয়া যায়নি।"

    return final_serials, invalid_lines, error_message